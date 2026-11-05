import faiss
import numpy as np

from rag.curriculum import heuristic_topics
from rag.embeddings import LOCAL_NAME, LocalHashEmbedder, get_embedder
from rag.pipeline import chunk_pages, extract_pages, ingest_document, retrieve_context
from rag.vector_store import DocumentIndex, delete_index, index_exists, load_index


def test_local_embeddings_are_stable_and_normalizable():
    e = LocalHashEmbedder()
    a = e.embed_documents(["learning rate controls step size"])
    b = e.embed_documents(["learning rate controls step size"])
    assert a.shape == (1, e.dim)
    assert np.array_equal(a, b)  # md5-based: same text, same vector, every run


def test_offline_mode_uses_local_embedder():
    assert get_embedder().name == LOCAL_NAME


def test_faiss_index_returns_nearest_chunk_first():
    vectors = np.eye(4, dtype="float32")
    chunks = [{"text": f"chunk {i}", "page": i + 1, "chunk_id": str(i)} for i in range(4)]
    idx = DocumentIndex.build("unit", "test@4", vectors, chunks)
    assert isinstance(idx.index, faiss.IndexFlatIP)
    hits = idx.search(np.array([0.1, 0.9, 0.0, 0.0], dtype="float32"), k=2)
    assert hits[0]["page"] == 2
    assert hits[0]["score"] > hits[1]["score"]


def test_index_saves_and_loads_from_disk():
    vectors = np.random.RandomState(0).rand(5, 8).astype("float32")
    chunks = [{"text": f"c{i}", "page": 1, "chunk_id": str(i)} for i in range(5)]
    DocumentIndex.build("persist", "test@8", vectors, chunks, "f.pdf").save()
    assert index_exists("persist")
    loaded = load_index("persist")
    assert loaded.index.ntotal == 5 and loaded.embedder_name == "test@8"
    delete_index("persist")
    assert not index_exists("persist")


def test_pdf_ingest_and_retrieval_finds_the_right_page(sample_pdf):
    pages = extract_pages(sample_pdf)
    assert len(pages) == 3 and chunk_pages(pages)
    result = ingest_document(sample_pdf, "doc1", "ml_notes.pdf")
    assert result["chunks_count"] >= 3
    assert result["embedder"] == LOCAL_NAME

    hits = retrieve_context("What does Lasso regression do to the weights?", ["doc1"], k=2)
    assert hits[0]["page"] == 3
    hits = retrieve_context("stochastic gradient descent random training instance", ["doc1"], k=1)
    assert hits[0]["page"] == 2


def test_heuristic_curriculum_keeps_reading_order(sample_pdf):
    topics = heuristic_topics(extract_pages(sample_pdf))
    assert topics[:3] == ["Gradient Descent", "Stochastic Gradient Descent", "Regularization"]


def test_unknown_document_returns_nothing():
    assert retrieve_context("anything", ["does-not-exist"]) == []
