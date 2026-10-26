import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATA = Path(os.getenv("RAG_DATA_DIR", "data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
engine = create_async_engine(f"sqlite+aiosqlite:///{DATA / 'knowledge.db'}")
Session = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(connection, _):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(default="member")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires: Mapped[float] = mapped_column(Float)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    size: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64), index=True)
    department: Mapped[str] = mapped_column(String(60), default="General")
    status: Mapped[str] = mapped_column(default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(150), default="New conversation")
    created_at: Mapped[str] = mapped_column(default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(15))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default="completed")
    created_at: Mapped[str] = mapped_column(default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[str] = mapped_column(default=now)


class Query(Base):
    __tablename__ = "queries"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    found: Mapped[bool] = mapped_column(Boolean)
    provider: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[str] = mapped_column(default=now)
