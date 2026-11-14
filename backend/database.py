"""Rama — database layer (SQLAlchemy + SQLite).

Tables:
- Conversation: ek chat thread (title + created_at)
- Message: ek message (user ya assistant) — conversation se linked
- Memory: long-term yaadein (key/value) — "yaad rakho" se banti hain

DATABASE_URL env se aata hai, default sqlite:///./rama.db
"""
import os

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rama.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), default="New chat")
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(20), nullable=False)  # "user" ya "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    conversation = relationship("Conversation", back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), nullable=False, index=True)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


def init_db() -> None:
    """Saari tables banao (agar pehle se hain to kuch nahi hoga)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — ek request ke liye ek session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
