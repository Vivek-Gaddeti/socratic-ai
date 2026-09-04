"""
SocraticAI — FastAPI Main Application
"""
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database.models import init_db
from routers import auth, documents, chat
from config import get_settings

settings = get_settings()

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database
    await init_db()
    print("[OK] SocraticAI Server started!")
    print(f"[INFO] Web UI: http://127.0.0.1:8000")
    print(f"[INFO] API Docs: http://127.0.0.1:8000/docs")
    yield
    # Shutdown
    print("[INFO] SocraticAI Server shutting down...")


app = FastAPI(
    title="SocraticAI API",
    description="Multi-Agent RAG-powered Socratic learning platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)

# Mount static folder
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "app": "SocraticAI",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


from pydantic import BaseModel


class ApiKeyUpdate(BaseModel):
    api_key: str


@app.get("/api/settings")
async def get_app_settings():
    current_settings = get_settings()
    key = current_settings.gemini_api_key or ""
    has_key = bool(key and "your_gemini" not in key and len(key) >= 15)
    masked = f"{key[:6]}...{key[-4:]}" if has_key else "Not configured"
    return {
        "has_api_key": has_key,
        "masked_key": masked,
        "mode": "Gemini 1.5 Flash (Cloud AI)" if has_key else "Local Socratic Engine (Offline Heuristics)",
    }


@app.post("/api/settings/api-key")
async def save_api_key(req: ApiKeyUpdate):
    clean_key = req.api_key.strip()
    os.environ["GEMINI_API_KEY"] = clean_key

    # Update .env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(env_path, "w", encoding="utf-8") as f:
            key_written = False
            for line in lines:
                if line.startswith("GEMINI_API_KEY="):
                    f.write(f"GEMINI_API_KEY={clean_key}\n")
                    key_written = True
                else:
                    f.write(line)
            if not key_written:
                f.write(f"GEMINI_API_KEY={clean_key}\n")

    # Clear lru_cache
    get_settings.cache_clear()

    return {"status": "ok", "message": "Gemini API key updated successfully!"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    print("[INFO] Starting SocraticAI server on http://127.0.0.1:8000 ...")
    try:
        webbrowser.open("http://127.0.0.1:8000")
    except Exception:
        pass
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

