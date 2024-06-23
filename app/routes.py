from flask import render_template, request, jsonify
from app import app
from app.chatbot import get_chatbot_response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get("message")
    chatbot_response = get_chatbot_response(user_message)
    return jsonify(response=chatbot_response)
