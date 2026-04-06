from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from groq import Groq
import os, uuid, json
from datetime import datetime
from database import db, Conversation, Message, InterviewSession
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chattutor-v2-secret")
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chattutor.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024   # 5 MB upload limit
db.init_app(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama3-70b-8192"

# ── System prompts ─────────────────────────────────────────────────────────────

TUTOR_PROMPTS = {
    "normal": (
        "You are ChatTutor, a smart and friendly AI tutor for students. "
        "Answer clearly with examples. Keep focused (3–5 sentences unless more depth is needed). "
        "After answering, suggest one follow-up topic."
    ),
    "eli5": (
        "You are ChatTutor. Explain like the student is 5 years old. "
        "Simple words, fun real-life analogies, zero jargon. Max 5 sentences."
    ),
    "exam": (
        "You are ChatTutor in exam mode. SHORT, precise, exam-ready answers. "
        "Format: 1-line definition, then 2–3 bullet points. Max 6 lines. No fluff."
    ),
}

INTERVIEW_SYSTEM = """You are an expert AI interviewer conducting a mock interview.
You have been given the candidate's profile: name, role they're applying for, and skills/background.

RULES:
1. Ask ONE question at a time — never multiple questions together.
2. After the candidate answers, give structured feedback IMMEDIATELY in this exact JSON format:
{
  "feedback": {
    "content_score": <1-10>,
    "confidence_score": <1-10>,
    "content_feedback": "<2-3 sentences on answer quality>",
    "suggestion": "<1 specific improvement tip>",
    "follow_up": "<one natural follow-up question OR null if moving to next topic>"
  },
  "next_question": "<the next interview question OR 'INTERVIEW_COMPLETE' if done>"
}
3. Vary question types: HR, Technical, Behavioral (STAR method).
4. After 8–10 questions, set next_question to "INTERVIEW_COMPLETE".
5. Always respond with ONLY the JSON — no extra text outside the JSON."""

SCORE_SYSTEM = """You are an expert interview coach. 
Analyze the complete interview transcript provided and return ONLY this JSON:
{
  "scores": {
    "communication": <1-10>,
    "technical": <1-10>,
    "behavioral": <1-10>,
    "confidence": <1-10>,
    "overall": <1-10>
  },
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "improvements": ["<area 1>", "<area 2>", "<area 3>"],
  "verdict": "<2-3 sentence overall assessment>",
  "hire_recommendation": "<Strong Yes / Yes / Maybe / No>"
}"""

RESUME_SYSTEM = """Extract key information from this resume/profile text and return ONLY this JSON:
{
  "name": "<candidate name or Unknown>",
  "role": "<most recent or target role>",
  "skills": ["<skill1>", "<skill2>", "<skill3>", ...],
  "experience_years": <number or 0>,
  "summary": "<2-3 sentence professional summary>"
}"""

WEAK_KEYWORDS = [
    "recursion","big-o","big o","pointers","dynamic programming",
    "normalization","joins","sql","deadlock","semaphore",
    "calculus","integration","differentiation","matrices",
    "linked list","binary tree","graph","sorting","hashing","heap",
    "networking","tcp","http","dns","osi",
]

def detect_weak(text):
    found, lower = [], text.lower()
    for kw in WEAK_KEYWORDS:
        if kw in lower and kw not in found:
            found.append(kw)
    return found[:3]

def groq_call(messages, system, temperature=0.7, max_tokens=1024):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":system}] + messages,
        max_tokens=max_tokens, temperature=temperature,
    )
    return resp.choices[0].message.content

def safe_json(text):
    """Extract JSON from LLM response even if it has extra text."""
    text = text.strip()
    # Find first { and last }
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_uid():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    get_uid()
    return render_template("index.html")

@app.route("/interview")
def interview_page():
    get_uid()
    return render_template("interview.html")

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — TUTOR API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/ask", methods=["POST"])
def ask():
    data       = request.get_json()
    question   = data.get("question","").strip()
    mode       = data.get("mode","normal")
    convo_id   = data.get("conversation_id")
    uid        = get_uid()

    if not question: return jsonify({"error":"Question required"}), 400
    if mode not in TUTOR_PROMPTS: mode = "normal"

    convo = Conversation.query.filter_by(id=convo_id, user_id=uid).first() if convo_id else None
    if not convo:
        convo = Conversation(user_id=uid, title=question[:60])
        db.session.add(convo); db.session.flush()
        convo_id = convo.id

    history = Message.query.filter_by(conversation_id=convo_id)\
        .order_by(Message.created_at.asc()).limit(10).all()
    messages = [{"role":m.role,"content":m.content} for m in history]
    messages.append({"role":"user","content":question})

    db.session.add(Message(conversation_id=convo_id, role="user", content=question, mode=mode))

    try:
        answer = groq_call(messages, TUTOR_PROMPTS[mode])
    except Exception as e:
        db.session.rollback()
        return jsonify({"error":str(e)}), 500

    db.session.add(Message(conversation_id=convo_id, role="assistant", content=answer, mode=mode))
    db.session.commit()

    return jsonify({
        "answer": answer,
        "conversation_id": convo_id,
        "weak_topics": detect_weak(question),
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat(),
    })

@app.route("/api/history")
def history():
    uid = get_uid()
    convos = Conversation.query.filter_by(user_id=uid)\
        .order_by(Conversation.created_at.desc()).limit(15).all()
    return jsonify([{"id":c.id,"title":c.title,"created_at":c.created_at.isoformat()} for c in convos])

@app.route("/api/conversation/<int:cid>")
def get_conversation(cid):
    uid = get_uid()
    convo = Conversation.query.filter_by(id=cid, user_id=uid).first()
    if not convo: return jsonify({"error":"Not found"}), 404
    msgs = Message.query.filter_by(conversation_id=cid).order_by(Message.created_at.asc()).all()
    return jsonify({"id":convo.id,"title":convo.title,
        "messages":[{"role":m.role,"content":m.content,"mode":m.mode} for m in msgs]})

@app.route("/api/weak-topics")
def weak_topics():
    uid = get_uid()
    convos = Conversation.query.filter_by(user_id=uid).all()
    ids = [c.id for c in convos]
    if not ids: return jsonify({"weak":[],"strong":[]})
    questions = Message.query.filter(
        Message.conversation_id.in_(ids), Message.role=="user").all()
    freq = {}
    for m in questions:
        for kw in detect_weak(m.content): freq[kw] = freq.get(kw,0)+1
    s = sorted(freq.items(), key=lambda x:x[1], reverse=True)
    return jsonify({"weak":[t[0] for t in s[:3]],"strong":[t[0] for t in s[3:6]]})

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — INTERVIEW API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/interview/start", methods=["POST"])
def interview_start():
    """
    Body: { name, role, skills, interviewer_mode }
    Returns: { session_id, first_question }
    """
    data = request.get_json()
    name  = data.get("name","Candidate").strip()
    role  = data.get("role","Software Engineer").strip()
    skills = data.get("skills","").strip()
    imode  = data.get("interviewer_mode","friendly")  # friendly | strict
    uid   = get_uid()

    profile = f"Candidate: {name}\nRole: {role}\nSkills/Background: {skills}"
    style   = "Be encouraging and supportive." if imode=="friendly" else \
              "Be direct, challenging, and professional. Push back on weak answers."

    system = INTERVIEW_SYSTEM + f"\n\nINTERVIEWER STYLE: {style}"

    # Ask AI for first question
    try:
        raw = groq_call(
            [{"role":"user","content":f"Start the interview. Profile:\n{profile}\n\nAsk the first question."}],
            system, temperature=0.8
        )
    except Exception as e:
        return jsonify({"error":str(e)}), 500

    parsed = safe_json(raw)
    first_q = parsed.get("next_question","Tell me about yourself.") if parsed else "Tell me about yourself."

    sess = InterviewSession(
        user_id=uid, name=name, role=role, skills=skills,
        interviewer_mode=imode,
        system_prompt=system,
        transcript=json.dumps([{"role":"assistant","content":first_q,"type":"question"}]),
        question_count=1,
    )
    db.session.add(sess); db.session.commit()

    return jsonify({"session_id":sess.id, "first_question":first_q, "name":name, "role":role})


@app.route("/api/interview/answer", methods=["POST"])
def interview_answer():
    """
    Body: { session_id, answer }
    Returns: { feedback, next_question, is_complete, question_number }
    """
    data = request.get_json()
    sid    = data.get("session_id")
    answer = data.get("answer","").strip()
    uid    = get_uid()

    sess = InterviewSession.query.filter_by(id=sid, user_id=uid).first()
    if not sess: return jsonify({"error":"Session not found"}), 404
    if not answer: return jsonify({"error":"Answer required"}), 400

    transcript = json.loads(sess.transcript)

    # Build messages for context
    messages = []
    for t in transcript:
        messages.append({"role": "assistant" if t["role"]=="assistant" else "user",
                         "content": t["content"]})
    messages.append({"role":"user","content":answer})

    try:
        raw = groq_call(messages, sess.system_prompt, temperature=0.7)
    except Exception as e:
        return jsonify({"error":str(e)}), 500

    parsed = safe_json(raw)
    if not parsed:
        # fallback
        parsed = {
            "feedback": {
                "content_score":7,"confidence_score":7,
                "content_feedback":"Good attempt. Keep elaborating with examples.",
                "suggestion":"Use the STAR method for structured answers.",
                "follow_up": None
            },
            "next_question": "Can you tell me about a challenging project you worked on?"
        }

    feedback    = parsed.get("feedback",{})
    next_q      = parsed.get("next_question","INTERVIEW_COMPLETE")
    is_complete = next_q == "INTERVIEW_COMPLETE"

    # Update transcript
    transcript.append({"role":"user","content":answer,"type":"answer"})
    if not is_complete:
        q_text = feedback.get("follow_up") or next_q
        transcript.append({"role":"assistant","content":q_text,"type":"question"})
    
    sess.transcript     = json.dumps(transcript)
    sess.question_count = sess.question_count + 1
    if is_complete: sess.completed = True
    db.session.commit()

    return jsonify({
        "feedback": feedback,
        "next_question": feedback.get("follow_up") or next_q,
        "is_complete": is_complete,
        "question_number": sess.question_count,
    })


@app.route("/api/interview/score/<int:sid>")
def interview_score(sid):
    """Generate final score dashboard for a completed interview."""
    uid  = get_uid()
    sess = InterviewSession.query.filter_by(id=sid, user_id=uid).first()
    if not sess: return jsonify({"error":"Not found"}), 404

    transcript = json.loads(sess.transcript)
    transcript_text = "\n".join(
        f"[{'INTERVIEWER' if t['role']=='assistant' else 'CANDIDATE'}]: {t['content']}"
        for t in transcript
    )

    try:
        raw = groq_call(
            [{"role":"user","content":f"Role applied for: {sess.role}\n\nTranscript:\n{transcript_text}"}],
            SCORE_SYSTEM, temperature=0.3
        )
    except Exception as e:
        return jsonify({"error":str(e)}), 500

    result = safe_json(raw)
    if not result:
        result = {
            "scores":{"communication":7,"technical":7,"behavioral":7,"confidence":7,"overall":7},
            "strengths":["Good communication","Relevant experience","Enthusiasm"],
            "improvements":["Add more specific examples","Improve technical depth","Practice STAR method"],
            "verdict":"Solid candidate with room for improvement.",
            "hire_recommendation":"Maybe"
        }

    return jsonify({**result, "name":sess.name, "role":sess.role,
                    "question_count":sess.question_count})


@app.route("/api/interview/parse-resume", methods=["POST"])
def parse_resume():
    """Parse plain-text resume pasted by user."""
    data = request.get_json()
    text = data.get("text","").strip()
    if not text: return jsonify({"error":"No text provided"}), 400

    try:
        raw = groq_call(
            [{"role":"user","content":f"Parse this resume:\n\n{text}"}],
            RESUME_SYSTEM, temperature=0.3
        )
    except Exception as e:
        return jsonify({"error":str(e)}), 500

    result = safe_json(raw)
    return jsonify(result or {"name":"","role":"","skills":[],"summary":""})


@app.route("/api/interview/sessions")
def interview_sessions():
    uid = get_uid()
    sessions = InterviewSession.query.filter_by(user_id=uid)\
        .order_by(InterviewSession.created_at.desc()).limit(10).all()
    return jsonify([{
        "id":s.id,"name":s.name,"role":s.role,
        "completed":s.completed,"question_count":s.question_count,
        "created_at":s.created_at.isoformat()
    } for s in sessions])


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)