"""Rama — FastAPI backend (entry point).

Run:
  pip install -r backend/requirements.txt
  # backend/.env me GEMINI_API_KEY daalo
  uvicorn main:app --reload --app-dir backend

Endpoints:
  GET  /              -> health check
  POST /chat          -> {message, conversation_id?} -> {answer, sources, conversation_id}
  POST /upload        -> multipart file -> {filename, chars}
  GET  /memories      -> saved memories
  POST /remember      -> {key, value} save
  GET  /conversations -> list conversations
"""
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_router import AIRouter
from database import Conversation, Message, Memory, get_db, init_db
from file_reader import extract_text_from_upload
from memory import handle_memory_command, save_memory
from security import CORS_ORIGINS, sanitize_input

load_dotenv()

app = FastAPI(title="Rama", description="Rama — AI chat app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = AIRouter()


@app.on_event("startup")
def startup():
    init_db()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    mode: str = "fast"  # "fast" (default) ya "deep" (step-by-step reasoning)


class RememberRequest(BaseModel):
    key: str
    value: str


@app.get("/")
def root():
    return {"status": "ok", "app": "Rama"}


@app.get("/health")
def health():
    """Render health check — iska response {"status": "healthy"} hona chahiye."""
    return {"status": "healthy"}


@app.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    message = sanitize_input(req.message)
    if not message:
        raise HTTPException(status_code=400, detail="Message khali hai.")

    # Conversation nikalo ya nayi banao
    conv = None
    if req.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == req.conversation_id).first()
    if conv is None:
        conv = Conversation(title=message[:60])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # User message save karo
    db.add(Message(conversation_id=conv.id, role="user", content=message))
    db.commit()

    # Memory command? ("yaad rakho ...", "mera naam X hai")
    mem_reply = handle_memory_command(message, db)
    if mem_reply:
        db.add(Message(conversation_id=conv.id, role="assistant", content=mem_reply))
        db.commit()
        return {"answer": mem_reply, "sources": [], "conversation_id": conv.id}

    # History (aakhri 10 messages) — context ke liye
    history = []
    try:
        past = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(10)
            .all()
        )
        history = [{"role": m.role, "content": m.content} for m in reversed(past)]
    except Exception:
        history = []

    # AI se jawab (mode: fast = seedha short jawab, deep = step-by-step detail)
    mode = (req.mode or "fast").lower()
    if mode not in ("fast", "deep"):
        mode = "fast"
    result = router.answer(message, db, history=history, mode=mode)
    answer = result.get("answer", "")
    sources = result.get("sources", [])

    db.add(Message(conversation_id=conv.id, role="assistant", content=answer))
    db.commit()

    return {"answer": answer, "sources": sources, "conversation_id": conv.id, "mode": mode}


@app.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    text = extract_text_from_upload(data, file.filename or "")
    # File ka content memory me save karo taaki uske baare me poochh sako
    # (error message ho to save mat karo — sirf asli content)
    if not text.startswith("PDF support") and not text.startswith("Sorry, sirf"):
        save_memory(db, f"file:{file.filename}", text[:20000])
    return {"filename": file.filename, "chars": len(text)}


@app.get("/memories")
def list_memories(db: Session = Depends(get_db)):
    memories = db.query(Memory).order_by(Memory.id.desc()).all()
    return [{"id": m.id, "key": m.key, "value": m.value} for m in memories]


@app.post("/remember")
def remember(req: RememberRequest, db: Session = Depends(get_db)):
    key = (req.key or "").strip()
    value = (req.value or "").strip()
    if not key or not value:
        raise HTTPException(status_code=400, detail="key aur value dono chahiye.")
    mem = save_memory(db, key, value)
    return {"id": mem.id, "key": mem.key, "value": mem.value}


@app.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    convs = db.query(Conversation).order_by(Conversation.id.desc()).all()
    return [{"id": c.id, "title": c.title} for c in convs]
