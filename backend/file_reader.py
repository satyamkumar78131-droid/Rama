"""Rama — file reading (sirf Python stdlib, koi extra package nahi).

- .txt / .md / .csv: UTF-8 text padho (max ~20000 chars)
- .pdf: PDF support installed nahi hai — saaf message do
- baaki extensions: sirf text files supported
"""
import os

MAX_CHARS = 20000
TEXT_EXTS = {".txt", ".md", ".csv"}


def read_file(path: str, filename: str) -> str:
    """Disk ki file padho. path = poora path, filename = dikhane ke liye naam."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return (
            "PDF support not installed hai. "
            "Is file ko .txt me convert karke dobara upload karo."
        )
    if ext not in TEXT_EXTS:
        return (
            "Sorry, sirf text files supported hain (.txt, .md, .csv). "
            f"'{ext or 'unknown'}' file nahi padh sakta."
        )
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except FileNotFoundError:
        return "File nahi mili."
    except Exception as e:
        return f"File padhne me error: {e}"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n... (file bahut lambi thi, pehle 20000 characters hi liye gaye)"
    return text


def extract_text_from_upload(file_bytes: bytes, filename: str) -> str:
    """Upload hui file ke bytes se text nikalo."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return (
            "PDF support not installed hai. "
            "Is file ko .txt me convert karke dobara upload karo."
        )
    if ext not in TEXT_EXTS:
        return (
            "Sorry, sirf text files supported hain (.txt, .md, .csv). "
            f"'{ext or 'unknown'}' file nahi padh sakta."
        )
    try:
        text = file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return f"File padhne me error: {e}"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n... (file bahut lambi thi, pehle 20000 characters hi liye gaye)"
    return text
