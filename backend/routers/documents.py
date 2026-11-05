"""
Documents router: upload PDFs, list them, re-index, delete.

Indexing (PyMuPDF -> chunks -> embeddings -> FAISS, plus the curriculum) runs
in a background worker thread so the upload request returns immediately.
"""
import asyncio
import os
import uuid

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import AsyncSessionLocal, Document, User, get_db
from rag.pipeline import ingest_document, remove_document
from rag.vector_store import index_exists
from routers.auth import get_current_user

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_MB = 25


def _upload_path(filename: str) -> str:
    folder = get_settings().upload_dir
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)


def _doc_payload(d: Document) -> dict:
    return {
        "id": d.id,
        "filename": d.original_name,
        "chunks_count": d.chunks_count or 0,
        "pages_count": d.pages_count or 0,
        "topics": d.topics or [],
        "embedder": d.embedder,
        "status": d.status,
        "error": d.error,
        "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
    }


async def process_document(document_id: str) -> None:
    """Index one document and record the result. Safe to call again to re-index."""
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, document_id)
        if not doc:
            return
        pdf_path, original_name = _upload_path(doc.filename), doc.original_name
        doc.status, doc.error = "processing", None
        await db.commit()

    try:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError("The uploaded PDF is missing from the uploads folder.")
        result = await asyncio.to_thread(ingest_document, pdf_path, document_id, original_name)
        values = {
            "status": "ready",
            "chunks_count": result["chunks_count"],
            "pages_count": result["pages_count"],
            "topics": result["topics"],
            "embedder": result["embedder"],
            "error": None if result["chunks_count"] else "No text found. Is this a scanned PDF?",
        }
    except Exception as e:
        values = {"status": "error", "error": str(e)[:500]}

    async with AsyncSessionLocal() as db:
        await db.execute(update(Document).where(Document.id == document_id).values(**values))
        await db.commit()


async def reindex_missing() -> None:
    """On startup: index documents that have no FAISS index yet (e.g. from older versions)
    or were interrupted mid-processing."""
    async with AsyncSessionLocal() as db:
        docs = (await db.execute(select(Document).where(or_(Document.status == "ready", Document.status == "processing")))).scalars().all()
        todo = [d.id for d in docs if d.status == "processing" or not index_exists(d.id) or not d.embedder]
    for document_id in todo:
        await process_document(document_id)


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"PDF is larger than {MAX_UPLOAD_MB} MB")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file doesn't look like a PDF")

    document_id = str(uuid.uuid4())
    safe_filename = f"{document_id}.pdf"
    async with aiofiles.open(_upload_path(safe_filename), "wb") as f:
        await f.write(content)

    doc = Document(
        id=document_id, user_id=current_user.id, filename=safe_filename,
        original_name=file.filename, status="processing",
    )
    db.add(doc)
    await db.commit()
    background_tasks.add_task(process_document, document_id)
    return _doc_payload(doc)


@router.get("/")
async def list_documents(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document).where(Document.user_id == current_user.id).order_by(Document.created_at.desc())
    )
    return [_doc_payload(d) for d in result.scalars().all()]


async def _owned_document(db: AsyncSession, document_id: str, user: User) -> Document:
    result = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}")
async def get_document(document_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _doc_payload(await _owned_document(db, document_id, current_user))


@router.post("/{document_id}/reindex")
async def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _owned_document(db, document_id, current_user)
    doc.status = "processing"
    await db.commit()
    background_tasks.add_task(process_document, document_id)
    return _doc_payload(doc)


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    doc = await _owned_document(db, document_id, current_user)
    pdf_path = _upload_path(doc.filename)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    remove_document(document_id)
    await db.delete(doc)
    await db.commit()
    return {"message": "Document deleted"}
