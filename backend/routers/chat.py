"""
Chat router: tutoring sessions, messages, and the student's proficiency.

A session walks an ordered curriculum (the document's topics). The pointer
`current_topic_index` moves forward only when the evaluator scores an answer
>= MASTERY_THRESHOLD. Proficiency is stored per user, so a new session skips
topics the student already mastered in earlier sessions.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import run_socratic_session
from config import MASTERY_THRESHOLD
from database.models import Document, KnowledgeState, Message, Session, User, get_db
from routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

REVIEW_AFTER_DAYS = 3


def iso(dt: Optional[datetime]) -> Optional[str]:
    """Timestamps are stored in UTC; mark them so browsers convert to local time."""
    return dt.isoformat() + "Z" if dt else None


class StartSessionRequest(BaseModel):
    document_id: Optional[str] = None
    topic: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


# ─────────────────────────────── helpers ───────────────────────────────
async def _get_session(db: AsyncSession, session_id: str, user: User) -> Session:
    result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id == user.id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _knowledge_rows(db: AsyncSession, user_id: str, document_id: Optional[str]) -> dict[str, KnowledgeState]:
    result = await db.execute(
        select(KnowledgeState).where(KnowledgeState.user_id == user_id, KnowledgeState.document_id == document_id)
    )
    return {row.concept: row for row in result.scalars().all()}


def _proficiency_vector(curriculum: list[str], rows: dict[str, KnowledgeState]) -> list[dict]:
    now = datetime.utcnow()
    vector = []
    for concept in curriculum:
        row = rows.get(concept)
        days = (now - row.last_reviewed).days if row and row.last_reviewed else None
        vector.append({
            "concept": concept,
            "mastery": round(row.mastery_score, 1) if row else 0.0,
            "best": round(row.best_score or 0, 1) if row else 0.0,
            "attempts": row.attempts if row else 0,
            "mastered": bool(row and (row.best_score or 0) >= MASTERY_THRESHOLD),
            "last_reviewed": iso(row.last_reviewed) if row else None,
            "review_due": days is not None and days >= REVIEW_AFTER_DAYS,
        })
    return vector


def _session_payload(session: Session, document: Optional[Document], vector: list[dict]) -> dict:
    curriculum = session.curriculum or []
    idx = session.current_topic_index or 0
    return {
        "id": session.id,
        "title": session.topic or (document.original_name if document else "Open discussion"),
        "document_id": session.document_id,
        "document_name": document.original_name if document else None,
        "curriculum": curriculum,
        "current_topic_index": idx,
        "current_topic": curriculum[idx] if idx < len(curriculum) else None,
        "completed": bool(curriculum) and idx >= len(curriculum),
        "mastery_threshold": MASTERY_THRESHOLD,
        "proficiency": vector,
        "created_at": iso(session.created_at),
    }


def _message_payload(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "agent_used": m.agent_used,
        "score": m.score,
        "hint_level": m.hint_level,
        "topic": m.topic,
        "sources": m.sources or [],
        "agent_trace": m.agent_trace or [],
        "timestamp": iso(m.timestamp),
    }


async def _get_document(db: AsyncSession, document_id: Optional[str], user: User) -> Optional[Document]:
    if not document_id:
        return None
    result = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    return result.scalar_one_or_none()


# ─────────────────────────────── sessions ───────────────────────────────
@router.post("/session")
async def start_session(
    req: StartSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a session. With a document, the session follows that document's curriculum."""
    document = await _get_document(db, req.document_id, current_user)
    if req.document_id and not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document and document.status != "ready":
        raise HTTPException(status_code=400, detail="This document is still being indexed. Try again in a moment.")

    topic = (req.topic or "").strip()
    curriculum = list(document.topics or []) if document else []
    if topic and topic not in curriculum:
        curriculum.insert(0, topic)  # the student asked for this topic explicitly
    if not curriculum:
        curriculum = [topic or "General discussion"]

    # Cross-session progress: start at the first topic not mastered yet.
    rows = await _knowledge_rows(db, current_user.id, req.document_id)
    start = 0
    if not topic:
        while start < len(curriculum) and (rows.get(curriculum[start]) and (rows[curriculum[start]].best_score or 0) >= MASTERY_THRESHOLD):
            start += 1
    else:
        start = curriculum.index(topic)

    session = Session(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        document_id=req.document_id,
        topic=document.original_name if document else (topic or "Open discussion"),
        curriculum=curriculum,
        current_topic_index=start,
    )
    db.add(session)

    # Save the tutor's opening question, so the student's first reply is graded as an answer.
    if start < len(curriculum):
        current = curriculum[start]
        opening = (f"Let's work on **{current}**. I'll ask questions rather than lecture, and once you score "
                   f"{MASTERY_THRESHOLD} or more we'll move to the next topic.\n\nTo start: what do you already know about {current}?")
    else:
        current = curriculum[-1]
        opening = "You've already mastered every topic in this document. Pick any topic to review, or ask me anything about it."
    greeting = Message(
        id=str(uuid.uuid4()), session_id=session.id, role="assistant", content=opening,
        agent_used="socrates", topic=current, timestamp=datetime.utcnow(),
    )
    db.add(greeting)
    await db.commit()
    payload = _session_payload(session, document, _proficiency_vector(curriculum, rows))
    payload["messages"] = [_message_payload(greeting)]
    return payload


@router.get("/sessions")
async def list_sessions(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.user_id == current_user.id).order_by(Session.created_at.desc())
    )
    docs = {d.id: d for d in (await db.execute(select(Document).where(Document.user_id == current_user.id))).scalars()}
    out = []
    for s in result.scalars().all():
        curriculum = s.curriculum or []
        idx = s.current_topic_index or 0
        out.append({
            "id": s.id,
            "title": s.topic or "Open discussion",
            "document_id": s.document_id,
            "document_name": docs[s.document_id].original_name if s.document_id in docs else None,
            "topics_total": len(curriculum),
            "topics_done": min(idx, len(curriculum)),
            "current_topic": curriculum[idx] if idx < len(curriculum) else None,
            "created_at": iso(s.created_at),
        })
    return out


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _get_session(db, session_id, current_user)
    document = await _get_document(db, session.document_id, current_user)
    rows = await _knowledge_rows(db, current_user.id, session.document_id)
    msgs = (await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.timestamp.asc())
    )).scalars().all()
    payload = _session_payload(session, document, _proficiency_vector(session.curriculum or [], rows))
    payload["messages"] = [_message_payload(m) for m in msgs]
    return payload


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_session(db, session_id, current_user)
    msgs = (await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.timestamp.asc())
    )).scalars().all()
    return [_message_payload(m) for m in msgs]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _get_session(db, session_id, current_user)
    await db.execute(delete(Message).where(Message.session_id == session.id))
    await db.delete(session)
    await db.commit()
    return {"message": "Session deleted"}


# ─────────────────────────────── one tutoring turn ───────────────────────────────
@router.post("/message")
async def send_message(req: ChatRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty")
    session = await _get_session(db, req.session_id, current_user)
    sent_at = datetime.utcnow()

    history_rows = (await db.execute(
        select(Message).where(Message.session_id == session.id).order_by(Message.timestamp.asc())
    )).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]
    assistant_rows = [m for m in history_rows if m.role == "assistant"]

    # Consecutive low scores and current hint level, from the most recent replies.
    consecutive_low = 0
    for m in reversed(assistant_rows):
        if m.score is None:
            continue
        if m.score >= 50:
            break
        consecutive_low += 1
    last = assistant_rows[-1] if assistant_rows else None
    hint_level = last.hint_level if last and last.hint_level else 0

    curriculum = session.curriculum or []
    idx = session.current_topic_index or 0
    current_topic = curriculum[idx] if idx < len(curriculum) else (curriculum[-1] if curriculum else "")
    next_topic = curriculum[idx + 1] if idx + 1 < len(curriculum) else None

    if session.document_id:
        document_ids = [session.document_id]
    else:  # open discussion: search all of the student's indexed documents
        document_ids = [d.id for d in (await db.execute(
            select(Document).where(Document.user_id == current_user.id, Document.status == "ready")
        )).scalars()]

    result = await run_socratic_session(
        user_message=message,
        conversation_history=history,
        document_ids=document_ids,
        current_topic=current_topic,
        next_topic=next_topic,
        consecutive_low_scores=consecutive_low,
        hint_level=hint_level,
    )
    score = result["evaluation_score"]

    db.add(Message(id=str(uuid.uuid4()), session_id=session.id, role="user", content=message, topic=current_topic, timestamp=sent_at))
    db.add(Message(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="assistant",
        content=result["response"],
        agent_used=result["agent_used"],
        score=score if score >= 0 else None,
        hint_level=result["hint_level"] if "hint" in result["agent_used"] else None,
        topic=current_topic,
        sources=result["sources"],
        agent_trace=result["agent_trace"],
        timestamp=datetime.utcnow(),
    ))

    # Update proficiency on this concept (running average + best score).
    if score >= 0 and current_topic:
        rows = await _knowledge_rows(db, current_user.id, session.document_id)
        row = rows.get(current_topic)
        if row:
            row.mastery_score = (row.mastery_score * row.attempts + score) / (row.attempts + 1)
            row.best_score = max(row.best_score or 0, score)
            row.attempts += 1
            row.last_reviewed = datetime.utcnow()
        else:
            db.add(KnowledgeState(
                id=str(uuid.uuid4()), user_id=current_user.id, document_id=session.document_id,
                concept=current_topic, mastery_score=score, best_score=score, attempts=1,
            ))

    # Advance to the next topic only after reaching the mastery threshold.
    advanced = False
    if result["mastery_achieved"] and idx < len(curriculum):
        session.current_topic_index = idx + 1
        advanced = True

    await db.commit()

    rows = await _knowledge_rows(db, current_user.id, session.document_id)
    document = await _get_document(db, session.document_id, current_user)
    return {
        "response": result["response"],
        "agent_used": result["agent_used"],
        "evaluation_score": score,
        "evaluation_feedback": result["evaluation_feedback"],
        "mastery_achieved": result["mastery_achieved"],
        "hint_level": result["hint_level"],
        "agent_trace": result["agent_trace"],
        "sources": result["sources"],
        "topic": current_topic,
        "advanced": advanced,
        "session": _session_payload(session, document, _proficiency_vector(curriculum, rows)),
    }


# ─────────────────────────────── proficiency ───────────────────────────────
@router.get("/knowledge-state")
async def get_knowledge_state(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Flat list of every concept the student has been scored on."""
    result = await db.execute(
        select(KnowledgeState).where(KnowledgeState.user_id == current_user.id).order_by(KnowledgeState.mastery_score.desc())
    )
    return [
        {
            "concept": s.concept,
            "mastery_score": round(s.mastery_score, 1),
            "best_score": round(s.best_score or 0, 1),
            "attempts": s.attempts,
            "document_id": s.document_id,
            "last_reviewed": iso(s.last_reviewed),
        }
        for s in result.scalars().all()
    ]


@router.get("/proficiency")
async def get_proficiency(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The student's proficiency vector for each document, ordered by its curriculum."""
    documents = (await db.execute(
        select(Document).where(Document.user_id == current_user.id, Document.status == "ready").order_by(Document.created_at.desc())
    )).scalars().all()
    out = []
    for doc in documents:
        rows = await _knowledge_rows(db, current_user.id, doc.id)
        curriculum = list(doc.topics or [])
        curriculum += [c for c in rows if c not in curriculum]  # topics the student added themselves
        vector = _proficiency_vector(curriculum, rows)
        out.append({
            "document_id": doc.id,
            "document_name": doc.original_name,
            "topics": vector,
            "vector": [t["mastery"] for t in vector],
            "mastered_count": sum(t["mastered"] for t in vector),
        })
    general = await _knowledge_rows(db, current_user.id, None)
    if general:
        vector = _proficiency_vector(list(general), general)
        out.append({
            "document_id": None,
            "document_name": "Open discussions",
            "topics": vector,
            "vector": [t["mastery"] for t in vector],
            "mastered_count": sum(t["mastered"] for t in vector),
        })
    return {"mastery_threshold": MASTERY_THRESHOLD, "documents": out}
