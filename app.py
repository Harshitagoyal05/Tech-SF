from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import os
import uuid
from datetime import datetime
from database1 import db, User, Conversation, Message
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chattutor-groq-secret-2024")
CORS(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chattutor.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ── Groq client (FREE) ─────────────────────────
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
GROQ_MODEL = "openai/gpt-oss-20b"   # Free, fast, very capable

# ── System prompts for each mode ───────────────
SYSTEM_PROMPTS = {
    "normal": (
        "You are ChatTutor, a smart and friendly AI tutor for students. "
        "Answer clearly with examples. Keep responses focused (3–5 sentences unless more depth is truly needed). "
        "After answering, suggest one relevant follow-up topic the student might explore next."
    ),
    "eli5": (
        "You are ChatTutor. The student wants a VERY simple explanation — like they are 5 years old. "
        "Use simple words, fun real-life analogies, zero jargon. Short sentences. Max 5 sentences."
    ),
    "exam": (
        "You are ChatTutor in exam mode. Give SHORT, precise, exam-ready answers. "
        "Format: 1-line definition, then 2–3 bullet points of key facts to memorize. Max 6 lines. No fluff."
    ),
}

WEAK_KEYWORDS = [
    "recursion", "big-o", "big o", "pointers", "dynamic programming", "dp",
    "normalization", "joins", "sql", "os scheduling", "deadlock", "semaphore",
    "calculus", "integration", "differentiation", "matrices", "determinant",
    "linked list", "binary tree", "graph", "sorting", "hashing", "heap",
    "process", "thread", "memory management", "virtual memory",
    "networking", "tcp", "http", "dns", "osi model",
]

def detect_weak_topics(text):
    lower = text.lower()
    return [kw for kw in WEAK_KEYWORDS if kw in lower][:3]


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── Routes ─────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('signup'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/ask", methods=["POST"])
@login_required
def ask():
    data = request.get_json()
    question = data.get("question", "").strip()
    mode = data.get("mode", "normal")
    conversation_id = data.get("conversation_id")
    user_id = current_user.id

    if not question:
        return jsonify({"error": "Question is required"}), 400
    if mode not in SYSTEM_PROMPTS:
        mode = "normal"

    # Get or create conversation
    convo = None
    if conversation_id:
        convo = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not convo:
        convo = Conversation(user_id=user_id, title=question[:60])
        db.session.add(convo)
        db.session.flush()
        conversation_id = convo.id

    # Build history (last 10 messages for context)
    history = Message.query.filter_by(conversation_id=conversation_id)\
        .order_by(Message.created_at.asc()).limit(10).all()
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": question})

    # Save user message
    db.session.add(Message(
        conversation_id=conversation_id, role="user",
        content=question, mode=mode
    ))

    # ── Call Groq API ──────────────────────────
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPTS[mode]}] + messages,
            max_tokens=1024,
            temperature=0.7,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Groq API error: {str(e)}"}), 500

    # Save assistant message
    db.session.add(Message(
        conversation_id=conversation_id, role="assistant",
        content=answer, mode=mode
    ))
    db.session.commit()

    return jsonify({
        "answer": answer,
        "conversation_id": conversation_id,
        "weak_topics": detect_weak_topics(question),
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/api/history")
@login_required
def history():
    user_id = current_user.id
    convos = Conversation.query.filter_by(user_id=user_id)\
        .order_by(Conversation.created_at.desc()).limit(15).all()
    return jsonify([{"id": c.id, "title": c.title,
                     "created_at": c.created_at.isoformat()} for c in convos])


@app.route("/api/conversation/<int:cid>")
@login_required
def get_conversation(cid):
    user_id = current_user.id
    convo = Conversation.query.filter_by(id=cid, user_id=user_id).first()
    if not convo:
        return jsonify({"error": "Not found"}), 404
    msgs = Message.query.filter_by(conversation_id=cid)\
        .order_by(Message.created_at.asc()).all()
    return jsonify({
        "id": convo.id, "title": convo.title,
        "messages": [{"role": m.role, "content": m.content,
                      "mode": m.mode} for m in msgs],
    })


@app.route("/api/weak-topics")
@login_required
def weak_topics():
    user_id = current_user.id
    convos = Conversation.query.filter_by(user_id=user_id).all()
    ids = [c.id for c in convos]
    if not ids:
        return jsonify({"weak": [], "strong": []})
    questions = Message.query.filter(
        Message.conversation_id.in_(ids), Message.role == "user"
    ).all()
    freq = {}
    for m in questions:
        for kw in detect_weak_topics(m.content):
            freq[kw] = freq.get(kw, 0) + 1
    sorted_t = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return jsonify({
        "weak":   [t[0] for t in sorted_t[:3]],
        "strong": [t[0] for t in sorted_t[3:6]],
    })


@app.route("/api/clear", methods=["POST"])
@login_required
def clear():
    # Optionally clear all conversations for the user
    Conversation.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)