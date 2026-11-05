"""
SocraticAI — FastAPI application.
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BACKEND_DIR, CHAT_MODEL, EMBEDDING_MODEL, MASTERY_THRESHOLD, get_settings, has_valid_gemini_key
from database.models import User, init_db
from routers import auth, chat, documents
from routers.auth import get_current_user

static_dir = os.path.join(BACKEND_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Build FAISS indexes for documents uploaded before this version (runs in the background).
    reindex_task = asyncio.create_task(documents.reindex_missing())
    print("[OK] SocraticAI started: http://127.0.0.1:8000  (API docs: /docs)")
    yield
    reindex_task.cancel()


app = FastAPI(
    title="SocraticAI API",
    description="Multi-agent, RAG-grounded Socratic tutor",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"app": "SocraticAI", "status": "running", "docs": "/docs"}


class ApiKeyUpdate(BaseModel):
    api_key: str


@app.get("/api/settings")
async def get_app_settings():
    online = has_valid_gemini_key()
    return {
        "has_api_key": online,
        "chat_model": CHAT_MODEL if online else None,
        "embedding_model": EMBEDDING_MODEL if online else "local-hash (offline)",
        "mastery_threshold": MASTERY_THRESHOLD,
        "mode": "Gemini 2.5 Flash" if online else "Offline mode",
    }


@app.post("/api/settings/api-key")
async def save_api_key(req: ApiKeyUpdate, current_user: User = Depends(get_current_user)):
    """Save a Gemini key to backend/.env. Requires a signed-in user."""
    clean_key = req.api_key.strip()
    os.environ["GEMINI_API_KEY"] = clean_key

    env_path = os.path.join(BACKEND_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    with open(env_path, "w", encoding="utf-8") as f:
        written = False
        for line in lines:
            if line.startswith("GEMINI_API_KEY="):
                f.write(f"GEMINI_API_KEY={clean_key}\n")
                written = True
            else:
                f.write(line)
        if not written:
            f.write(f"GEMINI_API_KEY={clean_key}\n")

    get_settings.cache_clear()
    return {"status": "ok", "message": "Gemini API key saved"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    try:
        webbrowser.open("http://127.0.0.1:8000")
    except Exception:
        pass
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
