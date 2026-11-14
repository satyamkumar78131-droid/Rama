"""Rama — long-term memory (SQLite Memory table).

- save_memory / get_memory / search_memories
- handle_memory_command: "yaad rakho ..." / "remember ..." /
  "mera naam X hai" / "my name is X" ko pakad ke save karta hai.

IMPORTANT: sawal wale shabd (kya/kaun/what/who) kabhi naam nahi ban sakte.
"mera naam kya hai" poochhne pe "Kya" naam save nahi hoga.
"""
import re

from sqlalchemy.orm import Session

from database import Memory

QUESTION_WORDS = {
    "kya", "kaun", "kahan", "kab", "kyun", "kaise", "kaisa", "kaisi",
    "kitne", "kitna", "kitni", "kis", "kisko", "kiski", "kiske",
    "what", "who", "where", "when", "why", "how", "which", "whose", "whom",
    "h", "hai", "ho", "hun", "hoon", "tha", "thi",
    "is", "are", "am", "was", "were", "a", "an", "the",
    "mera", "meri", "mere", "naam", "nam", "name",
    "yaad", "yad", "rakho", "rkhna", "remember", "please", "plz",
}

STOPWORDS = QUESTION_WORDS | {
    "ka", "ki", "ko", "se", "me", "ne", "pe", "par", "aur", "bhi",
    "toh", "to", "yeh", "woh", "ye", "wo", "is", "us", "in", "un",
    "of", "on", "for", "and", "or", "my", "your", "his",
    "her", "its", "it", "this", "that", "i", "you", "he", "she", "we",
    "they", "mujhe", "tumhe", "tumhara", "tumhari", "tumhare",
}


def content_words(text: str) -> list[str]:
    """Text se content words nikalo (stopwords hata ke, lowercase)."""
    words = re.findall(r"[a-zA-Z\u0900-\u097F]+", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def save_memory(db: Session, key: str, value: str) -> Memory:
    """Memory save karo — purani same key ho to update karo."""
    key = (key or "").strip()
    value = (value or "").strip()
    existing = db.query(Memory).filter(Memory.key == key).first()
    if existing:
        existing.value = value
        db.commit()
        db.refresh(existing)
        return existing
    mem = Memory(key=key, value=value)
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def get_memory(db: Session, key: str):
    """Ek key ki memory lo; na ho to None."""
    return db.query(Memory).filter(Memory.key == key).first()


def search_memories(db: Session, query: str) -> list[Memory]:
    """Query ke words se match karne wali memories lo (key + value me).

    Score = kitne query words match hue. Best match pehle.
    """
    words = content_words(query)
    if not words:
        return []
    memories = db.query(Memory).all()
    hits = []
    for mem in memories:
        hay = f"{mem.key} {mem.value}".lower()
        score = sum(1 for w in words if w in hay)
        if score >= 1:
            hits.append((score, mem))
    hits.sort(key=lambda x: -x[0])
    return [m for _, m in hits]


def _clean_name(raw: str) -> str | None:
    """Naam saaf karo. Sawal wala shabd ya khali ho to None."""
    words = re.findall(r"[a-zA-Z\u0900-\u097F]+", (raw or "").strip())
    stop = {
        "hai", "h", "hoon", "hun", "yaad", "yad", "rakho", "remember",
        "please", "plz", "mera", "meri", "mere", "name", "naam", "nam",
    }
    name_words = []
    for w in words:
        if w.lower() in stop:
            break
        name_words.append(w)
        if len(name_words) >= 2:
            break
    if not name_words:
        return None
    # Naam me sawal wala shabd nahi ho sakta ("kya" kabhi naam nahi)
    if any(w.lower() in QUESTION_WORDS for w in name_words):
        return None
    return " ".join(name_words)


def _save_fact(db: Session, fact: str) -> str:
    """Ek fact ko memory me save karo. Key nikalne ki koshish karo."""
    # "mera favourite colour neela hai" -> key="favourite colour"
    m = re.search(r"mera\s+(.+?)\s+(hai|h)\s*$", fact)
    if m:
        middle = m.group(1).strip().split()
        if len(middle) >= 2:
            key = " ".join(middle[:-1][:3])  # aakhri shabd (value) hatao
            save_memory(db, key, fact)
            return f"Yaad rakh liya! ✅ ({key})"
    # "my favourite colour is blue" -> key="favourite colour"
    m = re.search(r"my\s+(.+?)\s+is\s+(.+)", fact)
    if m:
        key = " ".join(m.group(1).strip().split()[:3])
        save_memory(db, key, fact)
        return f"Yaad rakh liya! ✅ ({key})"
    # Warna poora fact hi key/value
    key = " ".join(fact.split()[:4])
    save_memory(db, key, fact)
    return "Yaad rakh liya! ✅"


def handle_memory_command(text: str, db: Session) -> str | None:
    """Memory command pakdo aur save karo. Command na ho to None.

    Samajhta hai:
    - "my name is X" -> user_name = X
    - "mera naam X hai" / "mera nam X hai" -> user_name = X
    - "yaad rakho <fact>" -> fact save
    - "remember <fact>" -> fact save
    """
    if not text:
        return None
    low = text.lower().strip()

    # 1. "my name is X" — PEHLE check karo, kyunki isme "remember" bhi ho sakta hai
    m = re.search(r"my\s+name\s+is\s+(.+)", low)
    if m:
        name = _clean_name(m.group(1))
        if name:
            save_memory(db, "user_name", name)
            return f"Yaad rakh liya! ✅ Tumhara naam {name} hai."
        return None

    # 2. "mera naam/nam X hai"
    m = re.search(r"mera\s+naa?m\s+(.+)", low)
    if m:
        name = _clean_name(m.group(1))
        if name:
            save_memory(db, "user_name", name)
            return f"Yaad rakh liya! ✅ Tumhara naam {name} hai."
        return None

    # 3. "yaad rakho <fact>"
    m = re.search(r"yaad\s+rakho\s+(.+)", low)
    if m:
        fact = m.group(1).strip()
        if fact:
            return _save_fact(db, fact)

    # 4. "remember <fact>" (English)
    m = re.search(r"\bremember\s+(.+)", low)
    if m:
        fact = m.group(1).strip()
        if fact:
            return _save_fact(db, fact)

    return None
