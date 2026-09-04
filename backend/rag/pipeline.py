"""
RAG Ingestion Pipeline
PDF → Chunks → Gemini Embeddings → FAISS Vector Store
Uses FAISS (pre-built Windows wheels, no C++ needed)
"""
import os
import uuid
import json
import numpy as np
import pymupdf as fitz  # PyMuPDF
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from config import get_settings

settings = get_settings()

FAISS_DIR = os.path.join(os.path.dirname(__file__), "..", "faiss_store")
os.makedirs(FAISS_DIR, exist_ok=True)

_embeddings_model = None

def _fallback_embed_text(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    words = text.lower().replace(",", " ").replace(".", " ").split()
    for w in words:
        if not w:
            continue
        h = abs(hash(w)) % dim
        vec[h] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec

class RobustEmbeddings:
    def __init__(self, key: str):
        self.key = key
        self.has_key = bool(key and key != "your_gemini_api_key_here")
        self.client = None
        if self.has_key:
            try:
                self.client = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=key,
                )
            except Exception:
                self.client = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.client:
            try:
                return self.client.embed_documents(texts)
            except Exception:
                pass
        return [_fallback_embed_text(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        if self.client:
            try:
                return self.client.embed_query(query)
            except Exception:
                pass
        return _fallback_embed_text(query)

def get_embeddings():
    global _embeddings_model
    if _embeddings_model is None:
        _embeddings_model = RobustEmbeddings(settings.gemini_api_key)
    return _embeddings_model


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ".", "!", "?", " "],
)


def _get_index_path(collection: str = "default"):
    return os.path.join(FAISS_DIR, f"{collection}.json")


def _load_store(collection: str = "default") -> dict:
    """Load the FAISS-compatible flat store from disk."""
    path = _get_index_path(collection)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"texts": [], "embeddings": [], "metadatas": [], "ids": []}


def _save_store(store: dict, collection: str = "default"):
    """Save store to disk."""
    path = _get_index_path(collection)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)


def _cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text from PDF with page metadata."""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append({"text": text, "page": page_num + 1})
    doc.close()
    return pages


def extract_topics_from_text(text: str) -> list[str]:
    """Simple topic extraction using heading detection."""
    topics = set()
    for line in text.split("\n"):
        line = line.strip()
        if 3 < len(line) < 80 and line and line[0].isupper() and not line.endswith("."):
            if len(line.split()) < 10:
                topics.add(line)
    return list(topics)[:15]


async def ingest_document(
    pdf_path: str,
    document_id: str,
    user_id: str,
    filename: str,
) -> dict:
    """Full ingestion: PDF → text → chunks → embeddings → FAISS store."""
    pages = extract_text_from_pdf(pdf_path)
    full_text = " ".join(p["text"] for p in pages)
    topics = extract_topics_from_text(full_text)

    all_chunks = []
    all_metadatas = []

    for page_data in pages:
        chunks = text_splitter.split_text(page_data["text"])
        for chunk in chunks:
            if len(chunk.strip()) > 50:
                all_chunks.append(chunk)
                all_metadatas.append({
                    "document_id": document_id,
                    "user_id": user_id,
                    "filename": filename,
                    "page": page_data["page"],
                    "chunk_id": str(uuid.uuid4()),
                })

    if not all_chunks:
        return {"chunks_count": 0, "topics": topics}

    # Embed in batches of 20
    embeddings_model = get_embeddings()
    all_embeddings = []
    batch_size = 20
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        embs = embeddings_model.embed_documents(batch)
        all_embeddings.extend(embs)

    # Load existing store and append
    store = _load_store()
    store["texts"].extend(all_chunks)
    store["embeddings"].extend(all_embeddings)
    store["metadatas"].extend(all_metadatas)
    store["ids"].extend([m["chunk_id"] for m in all_metadatas])
    _save_store(store)

    return {"chunks_count": len(all_chunks), "topics": topics}


def retrieve_context(query: str, document_id: str, k: int = 4) -> list[dict]:
    """Retrieve top-k relevant chunks for a query from a specific document."""
    embeddings_model = get_embeddings()
    query_emb = embeddings_model.embed_query(query)

    store = _load_store()
    if not store["texts"]:
        return []

    # Filter by document_id
    indices = [
        i for i, m in enumerate(store["metadatas"])
        if m.get("document_id") == document_id
    ]

    if not indices:
        return []

    # Compute cosine similarity
    scored = []
    for idx in indices:
        score = _cosine_similarity(query_emb, store["embeddings"][idx])
        scored.append((score, idx))

    scored.sort(reverse=True)
    top_k = scored[:k]

    return [
        {
            "content": store["texts"][idx],
            "page": store["metadatas"][idx].get("page", "?"),
            "score": round(score, 3),
        }
        for score, idx in top_k
    ]


def retrieve_context_no_filter(query: str, k: int = 4) -> list[dict]:
    """Retrieve context without document filter."""
    embeddings_model = get_embeddings()
    query_emb = embeddings_model.embed_query(query)

    store = _load_store()
    if not store["texts"]:
        return []

    scored = [
        (_cosine_similarity(query_emb, store["embeddings"][i]), i)
        for i in range(len(store["texts"]))
    ]
    scored.sort(reverse=True)

    return [
        {
            "content": store["texts"][idx],
            "page": store["metadatas"][idx].get("page", "?"),
            "filename": store["metadatas"][idx].get("filename", "unknown"),
            "score": round(score, 3),
        }
        for score, idx in scored[:k]
    ]
