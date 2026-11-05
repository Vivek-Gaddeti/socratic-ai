"""
FAISS vector store: one index per uploaded document.

Files in faiss_store/:
  <document_id>.faiss      the FAISS IndexFlatIP (exact inner-product search)
  <document_id>.meta.json  chunk texts, page numbers, and which embedder built it

Vectors are L2-normalized before adding and searching, so inner product equals
cosine similarity. IndexFlatIP is exact search, which is the right choice for a
few thousand chunks per textbook; IndexIVFFlat or HNSW would be the next step
for millions of chunks.
"""
import json
import os
import threading

import faiss
import numpy as np

from config import get_settings

_cache: dict[str, tuple[float, "DocumentIndex"]] = {}
_lock = threading.Lock()


def _paths(document_id: str) -> tuple[str, str]:
    folder = get_settings().faiss_dir
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, document_id)
    return base + ".faiss", base + ".meta.json"


class DocumentIndex:
    def __init__(self, document_id: str, embedder_name: str, index: faiss.Index, chunks: list[dict], filename: str = ""):
        self.document_id = document_id
        self.embedder_name = embedder_name
        self.index = index
        self.chunks = chunks
        self.filename = filename

    @classmethod
    def build(cls, document_id: str, embedder_name: str, vectors: np.ndarray, chunks: list[dict], filename: str = ""):
        if len(chunks) != len(vectors):
            raise ValueError("Each chunk needs exactly one vector")
        vectors = np.ascontiguousarray(vectors, dtype="float32")
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        return cls(document_id, embedder_name, index, chunks, filename)

    def search(self, query_vector: np.ndarray, k: int = 4) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        query = np.ascontiguousarray(query_vector.reshape(1, -1), dtype="float32")
        faiss.normalize_L2(query)
        scores, ids = self.index.search(query, min(k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            chunk = self.chunks[idx]
            results.append({
                "content": chunk["text"],
                "page": chunk["page"],
                "score": round(float(score), 3),
                "document_id": self.document_id,
                "filename": self.filename,
            })
        return results

    def save(self) -> None:
        index_path, meta_path = _paths(self.document_id)
        # faiss.write_index fails on Windows paths with non-ASCII characters, so write the bytes ourselves.
        with open(index_path, "wb") as f:
            f.write(faiss.serialize_index(self.index).tobytes())
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "document_id": self.document_id,
                "embedder": self.embedder_name,
                "dim": self.index.d,
                "filename": self.filename,
                "chunks": self.chunks,
            }, f, ensure_ascii=False)
        with _lock:
            _cache.pop(self.document_id, None)


def index_exists(document_id: str) -> bool:
    index_path, meta_path = _paths(document_id)
    return os.path.exists(index_path) and os.path.exists(meta_path)


def load_index(document_id: str) -> DocumentIndex | None:
    """Load a document's index from disk, reusing the in-memory copy if unchanged."""
    if not index_exists(document_id):
        return None
    index_path, meta_path = _paths(document_id)
    mtime = os.path.getmtime(index_path)
    with _lock:
        cached = _cache.get(document_id)
        if cached and cached[0] == mtime:
            return cached[1]
    with open(index_path, "rb") as f:
        index = faiss.deserialize_index(np.frombuffer(f.read(), dtype="uint8"))
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    doc_index = DocumentIndex(document_id, meta["embedder"], index, meta["chunks"], meta.get("filename", ""))
    with _lock:
        _cache[document_id] = (mtime, doc_index)
    return doc_index


def delete_index(document_id: str) -> None:
    for path in _paths(document_id):
        if os.path.exists(path):
            os.remove(path)
    with _lock:
        _cache.pop(document_id, None)
