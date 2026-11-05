"""Gemini chat models, created only when a valid API key is configured."""
from langchain_google_genai import ChatGoogleGenerativeAI

from config import CHAT_MODEL, get_settings, has_valid_gemini_key


def describe_llm_error(error: Exception) -> str:
    """Short, user-facing reason a Gemini call failed."""
    text = str(error)
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
        return "Gemini quota used up (free tier allows 20 requests/day)"
    if "503" in text or "UNAVAILABLE" in text:
        return "Gemini is temporarily overloaded"
    if "API key" in text or "401" in text or "403" in text:
        return "Gemini rejected the API key"
    return "Gemini call failed"


def get_llms():
    """Return (chat_llm, eval_llm), or (None, None) when running offline.

    chat_llm is warmer (temperature 0.7) for teaching; eval_llm is near
    deterministic (0.1) so scores are consistent.
    """
    if not has_valid_gemini_key():
        return None, None
    key = get_settings().gemini_api_key.strip()
    try:
        chat_llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, google_api_key=key, temperature=0.7, max_retries=1, timeout=60)
        eval_llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, google_api_key=key, temperature=0.1, max_retries=1, timeout=60)
        return chat_llm, eval_llm
    except Exception:
        return None, None
