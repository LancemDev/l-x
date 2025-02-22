import os
import logging
from flask import Flask, request, jsonify, session
import openai
from dotenv import load_dotenv
from pinecone import Pinecone, SeverlessSpec
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict
import re
from functools import wraps
from werkzeug.exceptions import GatewayTimeout
from cachetools import TTLCache
from hashlib import md5

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set the OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')
pinecone_api_key = os.getenv('PINECONE_API_KEY')
pinecone_env = os.getenv('PINECONE_ENV')

# Initialize Pinecone
pc = Pinecone(
    api_key=os.getenv('PINECONE_API_KEY')
)

index_name = 'rag-demo'
vector_dimension = 1536
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=vector_dimension,
        metric="cosine",
        spec=SeverlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )
index = pc.Index(index_name)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize cache
response_cache = TTLCache(maxsize=100, ttl=3600)

def cache_key(user_input: str, session_token: str) -> str:
    """Generate cache key from input and session"""
    return md5(f"{user_input}:{session_token}".encode()).hexdigest()

def timeout_handler(seconds=25):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Timeout or error occurred: {str(e)}")
                raise GatewayTimeout("Request timed out. Please try again.")
        return wrapper
    return decorator

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def get_embedding_with_retry(text: str, timeout: int = 10) -> List[float]:
    """Get embeddings with retry logic for API failures"""
    try:
        return openai.Embedding.create(
            input=text,
            model="text-embedding-ada-002",
            timeout=timeout
        )['data'][0]['embedding']
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise

def preprocess_query(query: str) -> str:
    """Preprocess the user query to improve matching"""
    query = re.sub(r'\s+', ' ', query.strip())
    
    admin_terms = ['prefecture', 'visa', 'carte de sejour', 'titre de sejour']
    for term in admin_terms:
        if term.lower() in query.lower():
            continue
        for keyword in ['how', 'what', 'process', 'procedure']:
            if keyword in query.lower() and term not in query.lower():
                query = f"{query} regarding {term}"
                break
    
    return query

def get_relevant_context(query: str, top_k: int = 3, score_threshold: float = 0.7) -> Dict:
    """Get relevant context with metadata and scoring"""
    try:
        processed_query = preprocess_query(query)
        query_embedding = get_embedding_with_retry(processed_query, timeout=10)
        
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            timeout=10
        )
        
        relevant_contexts = []
        for match in results['matches']:
            if match.score > score_threshold:
                relevant_contexts.append({
                    'text': match.metadata['text'],
                    'score': match.score,
                    'source': match.metadata.get('source', 'Unknown')
                })
        
        return {
            'contexts': relevant_contexts,
            'query_understood': len(relevant_contexts) > 0,
            'top_score': max([ctx['score'] for ctx in relevant_contexts]) if relevant_contexts else 0
        }
    
    except Exception as e:
        logger.error(f"Error querying vector database: {str(e)}")
        return {'contexts': [], 'query_understood': False, 'top_score': 0}

def construct_prompt(user_input: str, context_data: Dict) -> str:
    """Construct an intelligent prompt based on context quality"""
    base_prompt = """You are an expert on French administrative processes for English speakers. You are a bot for the website formalitee.ai.
                    Use the following information from our blog documentation in the website formalitee.ai to answer the user's question. 
                    If the provided information is insufficient, combine it with your general knowledge.
                    If no relevant information about the specified query is found, do not mention the blog or any information in the blog.
                    Not all answers need to be in point form, but they should be clear and concise even if they are in a conversational paragraph form.
                    Ask the user for clarification if needed.
                    Give follow up questions at the end if needed.

                    For introductory messages, have some important fact derived from the blog documentation on the website formalitee.ai.

                    Let the response be less bulky and more conversational.
                """
    
    if context_data['contexts']:
        context_texts = [f"[Relevance: {ctx['score']:.2f}] {ctx['text']}" 
                        for ctx in context_data['contexts']]
        contexts = "\n\n".join(context_texts)
        
        return f"""{base_prompt}
        
        Relevant blog information:
        {contexts}
        
        User question: {user_input}
        
        Please provide a clear, step-by-step response, citing specific sources where possible."""
    else:
        return f"""{base_prompt}
        
        Note: I couldn't find specific information about this in our documentation, but I'll provide 
        guidance based on my general knowledge of French administrative processes.
        
        User question: {user_input}"""

def fallback_response(user_input: str) -> Dict:
    """Provide a fallback response when main processing fails"""
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=150,
            temperature=0.7,
            timeout=10
        )
        return {
            'response': completion.choices[0].message.content.strip(),
            'context_used': False,
            'fallback': True
        }
    except Exception as e:
        logger.error(f"Fallback response failed: {str(e)}")
        return {
            'response': "I apologize, but I'm having trouble processing your request at the moment. Please try again in a few moments.",
            'error': True
        }

@app.route('/generate_caption', methods=['POST'])
@timeout_handler(seconds=25)
def generate_caption():
    try:
        data = request.json
        tone = data.get('tone')
        length = data.get('length')
        
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Generate a {length} caption in a {tone} tone.",
            max_tokens=50
        )
        
        caption = response.choices[0].text.strip()
        return jsonify({'caption': caption})
    except Exception as e:
        logger.error(f"Error generating caption: {str(e)}")
        return jsonify({
            'error': 'Failed to generate caption',
            'details': str(e)
        }), 500

@app.route('/')
def home():
    return 'Hello, Pixers! We are cooking something up for you!'

@app.route('/about')
def about():
    return 'About'

if __name__ == '__main__':
    app.run(debug=True)