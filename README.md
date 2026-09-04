# SocraticAI 🧠
### Multi-Agent RAG-Powered Socratic Learning Platform

A full-stack AI tutor that teaches through dialectical Socratic questioning, grounded in your uploaded PDF textbooks via RAG (Retrieval-Augmented Generation).

---

## Tech Stack
- **Backend**: FastAPI + LangGraph (multi-agent orchestration) + FAISS (vector store)
- **AI**: Google Gemini 2.5 Flash via LangChain
- **Frontend**: Vanilla HTML, CSS, and JavaScript (no React/Node required)
- **Database**: SQLite (async via aiosqlite + SQLAlchemy)
- **Auth**: JWT tokens (python-jose)

---

## Features
- **Socratic Agent**: Never gives direct answers — guides through targeted questions
- **Evaluator Agent**: Scores student answers 0–100% for comprehension
- **Hint Agent**: Progressively unlocks graduated hints when student is stuck
- **RAG Pipeline**: Indexes PDF textbooks into FAISS, retrieves relevant passages for every question
- **Knowledge State Tracking**: Tracks mastery per concept across sessions
- **Mastery Progression**: Automatically advances to next concept when ≥ 85% mastery is achieved

---

## Quick Start (Local)

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Set your Gemini API key
# Edit backend/.env and set GEMINI_API_KEY=your_key

# 3. Run
python main.py
# OR double-click run.bat
```

Visit: **http://127.0.0.1:8000**

---

## Project Structure

```
socratic-ai/
├── backend/
│   ├── agents/
│   │   └── orchestrator.py     # LangGraph multi-agent system
│   ├── database/
│   │   └── models.py           # SQLAlchemy async models
│   ├── rag/
│   │   └── pipeline.py         # FAISS PDF ingestion & retrieval
│   ├── routers/
│   │   ├── auth.py             # Register, Login, JWT
│   │   ├── chat.py             # Socratic session & messaging
│   │   └── documents.py        # PDF upload & management
│   ├── static/
│   │   ├── index.html          # Clean Vanilla HTML UI
│   │   ├── style.css           # Dark mode modern design
│   │   └── app.js              # Frontend logic (no framework)
│   ├── auth.py                 # Password hashing & JWT utils
│   ├── config.py               # Settings from .env
│   ├── main.py                 # FastAPI app + static file serving
│   ├── Dockerfile              # Production Docker image
│   └── requirements.txt
├── docker-compose.yml          # One-command deployment
├── .env.example                # Environment variable template
├── .gitignore
├── run.py                      # Cross-platform launcher
├── run.bat                     # Windows double-click launcher
└── README.md
```

---

## Deployment

### Railway (Recommended — Free Tier)
1. Push to GitHub
2. Connect repo on [railway.app](https://railway.app)
3. Set Root Directory to `backend`
4. Add env vars: `GEMINI_API_KEY`, `SECRET_KEY`

### Docker
```bash
cp .env.example .env   # Fill in your GEMINI_API_KEY
docker-compose up -d
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key from [AI Studio](https://aistudio.google.com/app/apikey) |
| `SECRET_KEY` | JWT signing secret (any long random string) |
| `DATABASE_URL` | SQLite path (default) or PostgreSQL URL for production |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Login (returns JWT) |
| GET | `/auth/me` | Current user profile |
| POST | `/documents/upload` | Upload PDF for RAG |
| GET | `/documents/` | List indexed documents |
| POST | `/chat/session` | Start learning session |
| POST | `/chat/message` | Send message, get Socratic response |
| GET | `/chat/sessions` | List all sessions |
| GET | `/chat/knowledge-state` | Get mastery scores per concept |

Interactive docs: **http://localhost:8000/docs**
