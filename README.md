# SocraticAI

**A multi-agent RAG tutor that teaches your PDF textbooks through questions.**

Upload a PDF. SocraticAI indexes it in FAISS, asks Gemini to propose an ordered list of topics, and then tutors you one topic at a time. It asks questions grounded in the text, scores each answer from 0 to 100, gives graduated hints when you're stuck, and moves on to the next topic only when you score **85 or more**. Your proficiency on every topic is saved, so a new session picks up where you left off.

## How a turn works

```
student message
      │
      ▼
┌──────────────┐   top-4 passages from the document's FAISS index (cosine similarity)
│  Knowledge   │──────────────────────────────────────────────────────────────┐
└──────┬───────┘                                                              │
       ▼                                                                      │
┌──────────────┐   Gemini 2.5 Flash (temp 0.1) scores the answer 0-100         │
│  Evaluator   │   against the current topic; ≥ 85 = mastered                  │
└──────┬───────┘                                                              │
       ▼  route: asked for help, or 2 low scores in a row (< 40)?             │
   ┌───┴─────────────┐                                                        │
   ▼                 ▼                                                        │
┌────────┐      ┌────────┐   Gemini 2.5 Flash (temp 0.7) replies using the    │
│ Tutor  │      │  Hint  │   retrieved passages, citing page numbers  ◄────────┘
└────────┘      └────────┘   (hint levels 1 → 3)
```

The four agents are nodes in a **LangGraph** `StateGraph` (`backend/agents/orchestrator.py`). After the turn, the chat router updates the student's proficiency and, if the score reached 85, moves the session to the next topic.

## Features

- **RAG with FAISS.** PDF → PyMuPDF text → 800-character chunks (100 overlap) → `gemini-embedding-001` (768-dim) → one `faiss.IndexFlatIP` per document. Vectors are L2-normalized, so inner product equals cosine similarity.
- **Curriculum from the document.** Gemini reads the PDF and returns its key concepts in teaching order. Offline, headings are detected by font size and boldness.
- **Mastery gating.** A session's `current_topic_index` advances only when the evaluator scores ≥ 85 (`MASTERY_THRESHOLD` in `config.py`).
- **Proficiency vectors.** One row per (student, document, concept) with a running-average score, best score and attempt count. Read in curriculum order, they form the student's proficiency vector (`GET /chat/proficiency`).
- **Cross-session retention.** Progress belongs to the student, not the session. New sessions skip mastered topics, and topics not reviewed for 3+ days are flagged for review.
- **Works offline.** Without a Gemini key it uses a stable feature-hashing embedder, template questions and a keyword-overlap scorer, so the app and tests run without network access.
- **Web UI.** Vanilla HTML/CSS/JS, no build step: chat with citations, live curriculum panel, per-turn agent trace, library, progress dashboard, light/dark themes, works on phones.

## Run locally

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env      # then put your GEMINI_API_KEY in .env
python main.py               # opens http://127.0.0.1:8000  (API docs: /docs)
```

Or double-click `run.bat` on Windows. Get a free key at [Google AI Studio](https://aistudio.google.com/app/apikey).

## Tests

```bash
cd backend
python -m pytest tests -q
```

16 tests run fully offline on a temporary database. They cover:
- FAISS indexing and retrieval on a generated PDF
- index save and load
- offline embeddings, which must give the same vector for the same text every run
- curriculum extraction
- agent routing (hint vs. tutor)
- the end-to-end API flow: upload → session → answers → the topic advances at 85 → progress carries into the next session

## Project structure

```
backend/
├── main.py              FastAPI app, settings endpoints, startup re-indexing
├── config.py            settings + model names + MASTERY_THRESHOLD
├── llm.py               Gemini chat models (LangChain)
├── auth.py              bcrypt password hashing, JWT
├── agents/orchestrator.py   LangGraph: knowledge → evaluator → tutor | hint
├── rag/
│   ├── pipeline.py      PDF → pages → chunks → embeddings → FAISS; retrieval
│   ├── embeddings.py    Gemini embedder + offline hashing embedder
│   ├── vector_store.py  per-document FAISS IndexFlatIP, save/load
│   └── curriculum.py    ordered topic list (Gemini, or font-based headings)
├── routers/             auth, documents (upload/re-index/delete), chat (sessions, turns, proficiency)
├── database/models.py   SQLAlchemy models (SQLite) + lightweight migrations
├── static/              web UI (index.html, style.css, app.js)
└── tests/               pytest suite
```

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Create account / sign in (JWT) |
| GET | `/auth/me` | Current user |
| POST | `/documents/upload` | Upload a PDF (indexed in the background) |
| GET | `/documents/` | List documents with status, chunk count, curriculum |
| POST | `/documents/{id}/reindex` | Rebuild a document's FAISS index and curriculum |
| DELETE | `/documents/{id}` | Delete a document and its index |
| POST | `/chat/session` | Start a session (follows the document's curriculum) |
| GET | `/chat/sessions`, `/chat/sessions/{id}` | List sessions / session with messages |
| POST | `/chat/message` | One tutoring turn through the agent graph |
| GET | `/chat/proficiency` | Proficiency vector per document |
| GET | `/chat/knowledge-state` | Flat list of scored concepts |

## Deployment

`backend/Dockerfile` and `render.yaml` deploy the backend as one container. Set `GEMINI_API_KEY` and `SECRET_KEY`. SQLite and the FAISS files live on the container's disk, so mount a volume (see `docker-compose.yml`) to keep them.
