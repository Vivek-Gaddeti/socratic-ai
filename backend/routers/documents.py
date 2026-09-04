"""
Documents Router: Upload PDF, list documents, delete
"""
import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import Document, get_db, User
from routers.auth import get_current_user
from rag.pipeline import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def process_document_bg(
    pdf_path: str,
    document_id: str,
    user_id: str,
    filename: str,
    db_url: str,
):
    """Background task to ingest document into ChromaDB."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        result = await ingest_document(pdf_path, document_id, user_id, filename)

        async with session_maker() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    chunks_count=result["chunks_count"],
                    topics=result["topics"],
                    status="ready",
                )
            )
            await session.commit()
    except Exception as e:
        async with session_maker() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="error")
            )
            await session.commit()
    finally:
        await engine.dispose()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = str(uuid.uuid4())
    safe_filename = f"{document_id}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, safe_filename)

    # Save file to disk
    async with aiofiles.open(pdf_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # Create document record
    doc = Document(
        id=document_id,
        user_id=current_user.id,
        filename=safe_filename,
        original_name=file.filename,
        status="processing",
    )
    db.add(doc)
    await db.commit()

    # Start background ingestion
    from config import get_settings
    settings = get_settings()
    background_tasks.add_task(
        process_document_bg,
        pdf_path,
        document_id,
        current_user.id,
        file.filename,
        settings.database_url,
    )

    return {
        "document_id": document_id,
        "filename": file.filename,
        "status": "processing",
        "message": "Document uploaded! Processing in background...",
    }


@router.get("/")
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.original_name,
            "chunks_count": d.chunks_count,
            "topics": d.topics or [],
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "filename": doc.original_name,
        "chunks_count": doc.chunks_count,
        "topics": doc.topics or [],
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove from disk
    pdf_path = os.path.join(UPLOAD_DIR, doc.filename)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    await db.delete(doc)
    await db.commit()
    return {"message": "Document deleted"}
