"""
Chat Router: Socratic conversation sessions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from database.models import Session, Message, KnowledgeState, get_db, User, Document
from routers.auth import get_current_user
from agents.orchestrator import run_socratic_session
import uuid
from datetime import datetime

router = APIRouter(prefix="/chat", tags=["chat"])


class StartSessionRequest(BaseModel):
    document_id: Optional[str] = None
    topic: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


class QuizRequest(BaseModel):
    document_id: str
    num_questions: int = 5


@router.post("/session")
async def start_session(
    req: StartSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Socratic learning session."""
    session = Session(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        document_id=req.document_id,
        topic=req.topic,
    )
    db.add(session)
    await db.commit()
    return {"session_id": session.id}


@router.post("/message")
async def send_message(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in a Socratic session and get AI response."""
    # Verify session belongs to user
    result = await db.execute(
        select(Session).where(Session.id == req.session_id, Session.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Load conversation history
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == req.session_id)
        .order_by(Message.timestamp.asc())
    )
    messages = msg_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in messages]

    # Get consecutive low scores from recent history
    recent_scores = [m.score for m in messages[-4:] if m.score is not None and m.role == "assistant"]
    consecutive_low = sum(1 for s in reversed(recent_scores) if s < 50)

    # Get current hint level
    hint_msgs = [m for m in messages if m.hint_level is not None]
    hint_level = hint_msgs[-1].hint_level if hint_msgs else 0

    # Reset hint level if student is doing better
    if recent_scores and recent_scores[-1] and recent_scores[-1] >= 60:
        hint_level = 0
        consecutive_low = 0

    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=req.session_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)

    # Run multi-agent system
    agent_result = await run_socratic_session(
        user_message=req.message,
        conversation_history=history,
        document_id=session.document_id,
        consecutive_low_scores=consecutive_low,
        hint_level=hint_level,
        current_concept=session.topic or "",
    )

    # Save assistant message
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        session_id=req.session_id,
        role="assistant",
        content=agent_result["response"],
        agent_used=agent_result["agent_used"],
        score=agent_result["evaluation_score"] if agent_result["evaluation_score"] >= 0 else None,
        hint_level=agent_result["hint_level"] if "hint" in agent_result["agent_used"] else None,
    )
    db.add(assistant_msg)

    # Update knowledge state if concept identified
    if agent_result["current_concept"] and agent_result["evaluation_score"] >= 0:
        concept = agent_result["current_concept"]
        ks_result = await db.execute(
            select(KnowledgeState).where(
                KnowledgeState.user_id == current_user.id,
                KnowledgeState.concept == concept,
                KnowledgeState.document_id == session.document_id,
            )
        )
        ks = ks_result.scalar_one_or_none()
        score = agent_result["evaluation_score"]

        if ks:
            # Rolling average
            ks.mastery_score = (ks.mastery_score * ks.attempts + score) / (ks.attempts + 1)
            ks.attempts += 1
            ks.last_reviewed = datetime.utcnow()
        else:
            ks = KnowledgeState(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                document_id=session.document_id,
                concept=concept,
                mastery_score=score,
                attempts=1,
            )
            db.add(ks)

    await db.commit()

    return {
        "response": agent_result["response"],
        "agent_used": agent_result["agent_used"],
        "evaluation_score": agent_result["evaluation_score"],
        "mastery_achieved": agent_result["mastery_achieved"],
        "sources": agent_result["sources"],
        "current_concept": agent_result["current_concept"],
    }


@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions for the current user."""
    result = await db.execute(
        select(Session)
        .where(Session.user_id == current_user.id)
        .order_by(Session.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "document_id": s.document_id,
            "topic": s.topic,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a session."""
    # Verify ownership
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.timestamp.asc())
    )
    messages = msg_result.scalars().all()

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "agent_used": m.agent_used,
            "score": m.score,
            "hint_level": m.hint_level,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in messages
    ]


@router.get("/knowledge-state")
async def get_knowledge_state(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all concepts and mastery scores for the current user."""
    result = await db.execute(
        select(KnowledgeState)
        .where(KnowledgeState.user_id == current_user.id)
        .order_by(KnowledgeState.mastery_score.desc())
    )
    states = result.scalars().all()
    return [
        {
            "concept": s.concept,
            "mastery_score": round(s.mastery_score, 1),
            "attempts": s.attempts,
            "document_id": s.document_id,
            "last_reviewed": s.last_reviewed.isoformat(),
        }
        for s in states
    ]
