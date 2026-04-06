from collections import defaultdict

VAGUE_TRIGGERS = ["it", "this", "that", "explain more", "tell me more", "go on", "continue"]

TOPIC_MAP = {
    "fitness":  ["bmi", "bmr", "calories", "fitness", "workout", "exercise", "diet"],
    "coding":   ["python", "code", "function", "loop", "variable", "array", "debug"],
    "math":     ["calculus", "algebra", "equation", "integral", "derivative", "matrix"],
    "history":  ["war", "revolution", "empire", "civilization", "treaty", "medieval"],
    "biology":  ["cell", "dna", "protein", "mitosis", "organism", "genetics", "enzyme"],
    "physics":  ["force", "velocity", "energy", "gravity", "newton", "momentum", "wave"],
}

CONFUSION_WORDS = ["don't understand", "confused", "not clear", "explain again", "lost", "huh"]
MASTERY_WORDS   = ["got it", "makes sense", "i see", "understand now", "clear now", "perfect"]


def apply_explanation_mode(text, mode):
    prefixes = {
        "simple":   "Break this down in the simplest way possible: ",
        "detailed": "Give a thorough, in-depth explanation of: ",
        "example":  "Use a real-world example to explain: ",
    }
    prefix = prefixes.get(mode)
    return f"{prefix}{text}" if prefix else text


def resolve_ambiguity(text, memory):
    lowered = text.lower()
    if any(t in lowered for t in VAGUE_TRIGGERS):
        if memory:
            prior = memory[-1].get("user")
            if prior:
                return f"Referring to the earlier question — {prior} — {text}"
    return text


def check_difficulty_shift(text, level):
    lowered = text.lower()
    if any(w in lowered for w in CONFUSION_WORDS):
        return max(1, level - 1)
    if any(w in lowered for w in MASTERY_WORDS):
        return min(3, level + 1)
    return level


def classify_topic(text):
    lowered = text.lower()
    for subject, keywords in TOPIC_MAP.items():
        if any(kw in lowered for kw in keywords):
            return subject
    return "general"


def log_topic(memory_data, topic):
    if "topics" not in memory_data:
        memory_data["topics"] = defaultdict(int)
    memory_data["topics"][topic] += 1
    return memory_data


def hint_mode_active(memory_data, topic, threshold=3):
    count    = memory_data.get("topics", {}).get(topic, 0)
    resolved = memory_data.get("resolved", {}).get(topic, False)
    return count >= threshold and not resolved


def mark_resolved(memory_data, topic):
    if "resolved" not in memory_data:
        memory_data["resolved"] = {}
    memory_data["resolved"][topic] = True
    return memory_data


def build_prompt(text, topic, difficulty, hint):
    level = {1: "beginner", 2: "intermediate", 3: "advanced"}.get(difficulty, "intermediate")
    if hint:
        return f"Guide the student with a question instead of a direct answer. Topic: {topic}. Student asked: {text}"
    return f"Answer for a {level} student studying {topic}: {text}"


def run_pipeline(user_input, memory, memory_data, mode, difficulty):
    user_input  = apply_explanation_mode(user_input, mode)
    user_input  = resolve_ambiguity(user_input, memory)
    difficulty  = check_difficulty_shift(user_input, difficulty)
    topic       = classify_topic(user_input)
    memory_data = log_topic(memory_data, topic)
    hint        = hint_mode_active(memory_data, topic)
    prompt      = build_prompt(user_input, topic, difficulty, hint)
    return prompt, memory_data, difficulty, topic


def print_status(memory_data, difficulty, memory):
    level = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}.get(difficulty, "Intermediate")
    print(f"\n  Difficulty  : {level}")
    print(f"  Topics      : {dict(memory_data.get('topics', {}))}")
    print(f"  History     : {len(memory)} turn(s)")
    if memory_data.get("topics"):
        top = max(memory_data["topics"], key=memory_data["topics"].get)
        print(f"  Top topic   : {top}")


def main():
    memory      = []
    memory_data = {}
    difficulty  = 1

    print("=" * 54)
    print("  ChatTutor — Feature Engine")
    print("=" * 54)
    print("  Commands:")
    print("    mode simple / mode detailed / mode example / mode normal")
    print("    status   — show session stats")
    print("    reset    — start over")
    print("    quit     — exit")
    print("=" * 54)

    mode = "normal"

    while True:
        try:
            user_input = input("\n  You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("\n  Session ended.")
            break

        if user_input.lower() == "reset":
            memory, memory_data, difficulty, mode = [], {}, 1, "normal"
            print("  Session reset.")
            continue

        if user_input.lower() == "status":
            print_status(memory_data, difficulty, memory)
            continue

        if user_input.lower().startswith("mode "):
            new_mode = user_input.split(" ", 1)[1].strip().lower()
            if new_mode in ("simple", "detailed", "example", "normal"):
                mode = new_mode
                print(f"  Mode set to: {mode}")
            else:
                print("  Valid modes: simple, detailed, example, normal")
            continue

        prompt, memory_data, difficulty, topic = run_pipeline(
            user_input, memory, memory_data, mode, difficulty
        )

        level = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}.get(difficulty)
        hint  = hint_mode_active(memory_data, topic)

        print(f"\n  Topic    : {topic}")
        print(f"  Level    : {level}")
        print(f"  Hint mode: {'ON' if hint else 'off'}")
        print(f"  Prompt   : {prompt}")

        memory.append({"user": user_input, "bot": "[LLM response goes here]"})


if __name__ == "__main__":
    main()
