"""
Text embedders used by the RAG pipeline.

- GeminiEmbedder: Google's gemini-embedding-001, truncated to 768 dims.
- LocalHashEmbedder: offline fallback (signed feature hashing of words and
  word pairs). Uses md5, so the same text always gets the same vector, even
  after a server restart.

Each embedder has a `name`. A FAISS index remembers which embedder built it,
and queries against that index must use the same embedder.
"""
import hashlib
import math
import re
import time

import numpy as np

from config import EMBEDDING_DIM, EMBEDDING_MODEL, get_settings, has_valid_gemini_key

LOCAL_DIM = 512
LOCAL_NAME = f"local-hash@{LOCAL_DIM}"
GEMINI_NAME = f"{EMBEDDING_MODEL}@{EMBEDDING_DIM}"

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
    "was", "were", "be", "been", "it", "this", "that", "these", "those", "as", "by",
    "at", "from", "we", "you", "i", "can", "do", "does", "what", "how", "why", "which",
}


class EmbedderUnavailable(RuntimeError):
    """Raised when an index needs an embedder we can't use right now."""


class LocalHashEmbedder:
    name = LOCAL_NAME
    dim = LOCAL_DIM

    def _features(self, text: str) -> list[str]:
        words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP_WORDS]
        return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype="float32")
        counts: dict[str, int] = {}
        for f in self._features(text):
            counts[f] = counts.get(f, 0) + 1
        for feature, count in counts.items():
            digest = hashlib.md5(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign * (1.0 + math.log(count))
        return vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._embed_one(t) for t in texts]) if texts else np.zeros((0, self.dim), "float32")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed_one(text)[None, :]


class GeminiEmbedder:
    name = GEMINI_NAME
    dim = EMBEDDING_DIM
    batch_size = 50

    def __init__(self, api_key: str):
        from google import genai

        self.client = genai.Client(api_key=api_key)

    def _embed(self, texts: list[str], task_type: str) -> np.ndarray:
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            for attempt in range(4):
                try:
                    result = self.client.models.embed_content(
                        model=EMBEDDING_MODEL, contents=batch, config=config
                    )
                    vectors.extend(e.values for e in result.embeddings)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)  # back off on rate limits
        return np.asarray(vectors, dtype="float32")

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "RETRIEVAL_QUERY")


def get_embedder(name: str | None = None):
    """Return the embedder called `name`, or the best one available."""
    if name is None:
        name = GEMINI_NAME if has_valid_gemini_key() else LOCAL_NAME
    if name == LOCAL_NAME:
        return LocalHashEmbedder()
    if name == GEMINI_NAME:
        if not has_valid_gemini_key():
            raise EmbedderUnavailable("This document was indexed with Gemini embeddings; add a Gemini API key to search it.")
        return GeminiEmbedder(get_settings().gemini_api_key.strip())
    raise EmbedderUnavailable(f"Unknown embedder '{name}'. Re-index the document.")
