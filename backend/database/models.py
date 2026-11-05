from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    chunks_count = Column(Integer, default=0)
    pages_count = Column(Integer, default=0)
    topics = Column(JSON, default=list)  # ordered curriculum
    embedder = Column(String, nullable=True)  # which embedding model built the FAISS index
    status = Column(String, default="processing")  # processing | ready | error
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    document_id = Column(String, nullable=True)
    topic = Column(String, nullable=True)  # session title / free-form topic
    curriculum = Column(JSON, default=list)  # topics to master, in order
    current_topic_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    agent_used = Column(String, nullable=True)  # socrates_* | hint_*
    score = Column(Float, nullable=True)
    hint_level = Column(Integer, nullable=True)
    topic = Column(String, nullable=True)  # topic being studied when this was sent
    sources = Column(JSON, nullable=True)  # RAG citations shown with the reply
    agent_trace = Column(JSON, nullable=True)  # which agents ran this turn
    timestamp = Column(DateTime, default=datetime.utcnow)


class KnowledgeState(Base):
    """One row per (user, document, concept): the student's proficiency on that concept.

    Read together for one document, these rows form the student's proficiency
    vector over that document's curriculum. Rows belong to the user, not a
    session, so progress carries over between sessions.
    """
    __tablename__ = "knowledge_state"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    document_id = Column(String, nullable=True)
    concept = Column(String, nullable=False)
    mastery_score = Column(Float, default=0.0)  # running average of evaluator scores
    best_score = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    last_reviewed = Column(DateTime, default=datetime.utcnow)


# Columns added after the first release. SQLite's create_all() won't add
# columns to existing tables, so add any that are missing.
_ADDED_COLUMNS = {
    "documents": {"pages_count": "INTEGER DEFAULT 0", "embedder": "VARCHAR", "error": "TEXT"},
    "sessions": {"curriculum": "JSON", "current_topic_index": "INTEGER DEFAULT 0"},
    "messages": {"topic": "VARCHAR", "sources": "JSON", "agent_trace": "JSON"},
    "knowledge_state": {"best_score": "FLOAT DEFAULT 0"},
}


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            for table, columns in _ADDED_COLUMNS.items():
                existing = {row[1] for row in (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()}
                for name, ddl in columns.items():
                    if name not in existing:
                        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        # Rows from before best_score existed: the best score is at least the running average.
        await conn.execute(text(
            "UPDATE knowledge_state SET best_score = mastery_score "
            "WHERE best_score IS NULL OR best_score < mastery_score"
        ))


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
