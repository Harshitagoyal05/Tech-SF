from flask import render_template 
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

#LOAD MEMORY
def load_memory():
    try:
        with open("memory.json", "r") as f:
            return json.load(f)
    except:
        return []

#SAVE MEMORY
def save_memory(memory):
    with open("memory.json", "w") as f:
        json.dump(memory, f, indent=2)

# ROUTES 
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_input = data.get("question")

    # if empty input
    if not user_input:
        return jsonify({"answer": "Please ask a valid question."})

    memory = load_memory()

    # Store user message
    memory.append({"role": "user", "content": user_input})

    context=memory[-5:] # last 5 messages will be stored 

    # Temporary response : AI will be added later
    answer = "Context length: "+str(len(context))+" | You asked: " + user_input

    # Store bot reply
    memory.append({"role": "assistant", "content": answer})

    # PREVENT OVERFLOW
    memory=memory[-20:]   # keep last 20 messages only

    save_memory(memory)

    return jsonify({"answer": answer})

# RUN
if __name__=="__main__":
    app.run(debug=True)