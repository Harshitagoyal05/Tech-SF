# ChatTutor AI

A Flask-based AI tutor application powered by Groq's free API.

## Features

- AI-powered tutoring with multiple modes (Normal, ELI5, Exam)
- User authentication and conversation history
- Weak topic tracking
- Voice input
- **Document reader**: Upload documents to extract text and ask questions

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Create a `.env` file with:
     ```
     SECRET_KEY=your-secret-key-here
     GROQ_API_KEY=your-groq-api-key-here
     ```

4. Run the app:
   ```bash
   python app.py
   ```

5. Open http://localhost:5000 in your browser

## Usage

- Sign up or log in
- Ask questions in text, voice, or by uploading documents to extract text
- Switch between Normal, ELI5, and Exam modes
- View conversation history and weak topics