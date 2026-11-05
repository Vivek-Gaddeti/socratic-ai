"""
RAG pipeline: PDF -> page text (PyMuPDF) -> chunks -> embeddings -> FAISS index.

ingest_document() runs once per upload; retrieve_context() runs on every chat turn.
"""
import uuid

import numpy as np
import pymupdf as fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.curriculum import build_curriculum
from rag.embeddings import EmbedderUnavailable, get_embedder
from rag.vector_store import DocumentIndex, delete_index, load_index

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ".", "!", "?", " "],
)


def _page_lines(page) -> list[tuple[str, float, bool]]:
    """(text, font size, is_bold) for each line on a page."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if spans:
                text = "".join(s["text"] for s in spans).strip()
                size = max(s["size"] for s in spans)
                bold = all(s["flags"] & 16 for s in spans)
                lines.append((text, size, bold))
    return lines


def extract_pages(pdf_path: str) -> list[dict]:
    """Return [{"page", "text", "headings"}, ...] for pages that contain text.

    Headings are lines set in a larger or bold font than the body text; they
    become the document's curriculum when Gemini isn't available.
    """
    pages, all_lines = [], []
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                lines = _page_lines(page)
                all_lines.extend(lines)
                pages.append({"page": page_num, "text": text, "lines": lines})

    sizes = sorted(size for _, size, _ in all_lines)
    body_size = sizes[len(sizes) // 2] if sizes else 0
    for p in pages:
        p["headings"] = [t for t, size, bold in p.pop("lines") if size >= body_size * 1.15 or bold]
    return pages


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Split each page into overlapping chunks, keeping the page number for citations."""
    chunks = []
    for page in pages:
        for piece in text_splitter.split_text(page["text"]):
            if len(piece.strip()) > 50:
                chunks.append({"text": piece, "page": page["page"], "chunk_id": str(uuid.uuid4())})
    return chunks


def ingest_document(pdf_path: str, document_id: str, filename: str = "") -> dict:
    """Index one PDF. Blocking (network + CPU), so call it from a worker thread."""
    pages = extract_pages(pdf_path)
    chunks = chunk_pages(pages)
    embedder = get_embedder()

    if chunks:
        vectors = embedder.embed_documents([c["text"] for c in chunks])
    else:
        vectors = np.zeros((0, embedder.dim), dtype="float32")
    DocumentIndex.build(document_id, embedder.name, vectors, chunks, filename).save()

    return {
        "chunks_count": len(chunks),
        "pages_count": len(pages),
        "topics": build_curriculum(pages),
        "embedder": embedder.name,
    }


def retrieve_context(query: str, document_ids: list[str], k: int = 4) -> list[dict]:
    """Top-k chunks for `query` across the given documents, best first."""
    results, query_vectors = [], {}
    for document_id in document_ids:
        index = load_index(document_id)
        if index is None:
            continue
        try:
            if index.embedder_name not in query_vectors:
                query_vectors[index.embedder_name] = get_embedder(index.embedder_name).embed_query(query)
        except EmbedderUnavailable:
            continue
        except Exception:
            continue  # embedding API error: answer without this document rather than fail the turn
        results.extend(index.search(query_vectors[index.embedder_name], k))
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:k]


def remove_document(document_id: str) -> None:
    delete_index(document_id)
