# ChatTutor AI

A Flask-based AI tutor application powered by Groq's free API.

## Features

- AI-powered tutoring with multiple modes (Normal, ELI5, Exam)
- User authentication and conversation history
- Weak topic tracking
- Voice input
- **Document and image OCR reader**: Upload documents or images to extract text and ask questions

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   > Note: Image OCR now prefers `easyocr` by default. If `easyocr` is not installed or you want to use Tesseract, set `OCR_ENGINE=pytesseract` in `.env`.
   > If you use `pytesseract`, you still need the Tesseract OCR engine installed on your system. On Windows, install it from https://github.com/tesseract-ocr/tesseract.
   > After installing, restart your terminal/VS Code so the PATH update is recognized.
   > If it still fails, set `TESSERACT_CMD` to the full path to `tesseract.exe` in your `.env` file, for example:
   > ```
   > TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
   > ```

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