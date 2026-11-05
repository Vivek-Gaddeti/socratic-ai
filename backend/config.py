import os
from functools import lru_cache

from pydantic_settings import BaseSettings

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# Model names live here so the whole app agrees on them.
CHAT_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768

# A student must score at least this much on the current topic to move on.
MASTERY_THRESHOLD = 85


class Settings(BaseSettings):
    gemini_api_key: str = ""
    secret_key: str = "socratic-ai-secret"
    database_url: str = "sqlite+aiosqlite:///./socratic_ai.db"
    faiss_dir: str = os.path.join(BACKEND_DIR, "faiss_store")
    upload_dir: str = os.path.join(BACKEND_DIR, "uploads")
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = os.path.join(BACKEND_DIR, ".env")
        extra = "ignore"

    def model_post_init(self, __context) -> None:
        # Resolve "sqlite:///./x.db" against the backend folder, so the same
        # database is used no matter which folder the server is started from.
        prefix = "sqlite+aiosqlite:///./"
        if self.database_url.startswith(prefix):
            path = os.path.join(BACKEND_DIR, self.database_url[len(prefix):])
            self.database_url = "sqlite+aiosqlite:///" + path.replace("\\", "/")


@lru_cache()
def get_settings():
    return Settings()


def has_valid_gemini_key() -> bool:
    key = (get_settings().gemini_api_key or "").strip()
    return bool(key) and "your_gemini" not in key and len(key) >= 15
