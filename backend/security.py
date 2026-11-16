"""Rama — security helpers.

- GEMINI_API_KEY env se (backend/.env file se bhi load hoti hai)
- Input sanitize: strip + max 4000 chars
- CORS origins (dev me sab allowed, prod me restrict karo)
"""
import os

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

# Dev ke liye sab origins allowed; PROD me yahan apne domain likho.
CORS_ORIGINS = ["*"]


def get_api_key() -> str:
    """GEMINI_API_KEY env se lo; na ho to empty string."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_hf_token() -> str:
    """HF_TOKEN env se lo (Hugging Face Inference — Qwen brain ke liye); na ho to empty string."""
    return os.getenv("HF_TOKEN", "").strip()


def check_api_key() -> bool:
    """Key set hai ya nahi."""
    return bool(get_api_key())


def require_key() -> str:
    """Key chahiye — na ho to 500 error (frontend ko saaf message milega)."""
    key = get_api_key()
    if not key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY set nahi hai. backend/.env me apni Gemini key daalo.",
        )
    return key


def sanitize_input(text: str) -> str:
    """User input saaf karo: strip + max 4000 chars (abuse rokne ke liye)."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > 4000:
        text = text[:4000]
    return text
