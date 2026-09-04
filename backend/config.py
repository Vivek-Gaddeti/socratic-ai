from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    gemini_api_key: str = ""
    secret_key: str = "socratic-ai-secret"
    database_url: str = "sqlite+aiosqlite:///./socratic_ai.db"
    chroma_persist_dir: str = "./chroma_db"
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
