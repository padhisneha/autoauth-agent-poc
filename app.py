from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from config import settings

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

genai.configure(api_key=settings.gemini_api_key)

@app.route('/')
def index():
    return app.send_static_file('autoauth-frontend.html')

@app.route('/api/claude', methods=['POST'])
def claude_proxy():
    data = request.json
    
    messages = data.get('messages', [])
    system = data.get('system', '')
    
    prompt = f"{system}\n\n{messages[-1]['content']}" if system else messages[-1]['content']
    
    model = genai.GenerativeModel(settings.llm_model)
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.0, "max_output_tokens": data.get('max_tokens', 2000)}
    )
    
    return jsonify({"content": [{"text": response.text}]})

if __name__ == '__main__':
    app.run(debug=True, port=5000)