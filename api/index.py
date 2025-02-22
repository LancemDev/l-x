import os
import logging
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict
from functools import wraps
from werkzeug.exceptions import GatewayTimeout

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

index_name = 'quickstart'
vector_dimension = 1536
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=vector_dimension,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )
index = pc.Index(index_name)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route('/generate_caption', methods=['POST'])
@timeout_handler(seconds=25)
def generate_caption():
    try:
        data = request.json
        tone = data.get('tone')
        length = data.get('length')
        
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"""
            You are a social media manager for a company, Pixer. You need to generate a caption for a new product launch.
            Generate a {length} caption in a {tone} tone.
            Feel free to add hashtags and emojis to make the caption more engaging.
            Product: Pixer 2.0
            """,
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