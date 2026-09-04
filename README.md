# SocraticAI — Multi-Agent RAG Socratic Learning Platform

**SocraticAI** is an AI-powered educational system that never spoon-feeds answers. Instead, it utilizes the classical **Socratic Method** to stimulate critical thinking and illuminate ideas through guided dialogue, real-time understanding scoring, and graduated hints.

---

## Key Features

1. **Multi-Agent State Machine (LangGraph)**:
   - **Knowledge Agent**: Performs semantic retrieval of textbook passages using vector similarity.
   - **Evaluator Agent**: Evaluates student responses on a 0-100 rubric, identifying misconceptions and mastery.
   - **Socrates Agent**: Generates probing, open-ended questions tailored to the student's mastery level.
   - **Hint Agent**: Triggers multi-level graduated hints (Level 1 conceptual -> Level 2 analogy -> Level 3 guided insight) when a student gets stuck.

2. **RAG Pipeline (PDF to Embeddings)**:
   - PyMuPDF text & page extraction
   - Recursive character text chunking
   - Gemini & semantic fallback vector embeddings
   - Persistent vector index storage

3. **Knowledge Mastery Graph**:
   - Concept-level mastery tracking (0-100%) stored in SQLite
   - Visual progress bars per topic and session history

4. **Modern UI / UX**:
   - Next.js 16 + React + Turbopack
   - Glassmorphic design with dark theme
   - Real-time chat with typing indicator, agent badges, and source drawer

---

## Quick Start

### 1. Running the Backend
```bash
cd backend
# Optional: add your Gemini API Key in .env
# GEMINI_API_KEY=your_key_here
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Running the Frontend
```bash
cd frontend
npm run dev
```
Access the application: [http://localhost:3000](http://localhost:3000)

### 3. Demo Credentials
- **Email**: `scholar@example.com`
- **Password**: `SecurePassword123!`
*(Or click "Sign Up" to register any new account)*
