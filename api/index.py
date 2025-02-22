from flask import Flask, request, jsonify
import openai
import os
import dotenv

app = Flask(__name__)

# Load environment variables
dotenv.load_dotenv()

# OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

@app.route('/generate_caption', methods=['POST'])
def generate_caption():
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

@app.route('/')
def home():
    return 'Hello, Pixers! We are cooking something up for you!'

@app.route('/about')
def about():
    return 'About'

if __name__ == '__main__':
    app.run(debug=True)