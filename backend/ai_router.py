"""Rama — AI router (SAIME wala proven flow).

Order (hamesha yahi):
1. Naam wale sawal — "tumhara naam kya hai" -> "Main Rama hoon";
   "mera naam kya hai" -> user_name memory se. Kabhi web search nahi.
2. Personal memory pehle — saved memory jawab de (>= 2 content words
   overlap) to web search BILKUL nahi.
3. Current/factual sawal — web_search + sources.
4. Warna BRAIN se jawab — pehle Qwen3-4B (HF Inference, free), na chale to
   Gemini (gemini-2.0-flash) fallback. Step by step, facts invent nahi karta.
5. Brain na ho / fail ho — web search ya imaandaar "nahi pata".

Jawab me kabhi HTML entities (&#x27;) ya citation markers ([1], [12]) nahi aate.
Har external call try/except me hai — kuch bhi crash nahi karta.
"""
import json
import re
import urllib.error
import urllib.request

try:
    from google import genai
except Exception:  # google-genai install na ho to bhi app chalegi
    genai = None

from memory import content_words, get_memory, search_memories
from security import get_api_key, get_hf_token
from web_search import web_search

MODEL = "gemini-2.0-flash"

# Qwen brain — HF Inference API (router, OpenAI-compatible). Koi nayi dependency
# nahi — sirf stdlib urllib. HF_TOKEN Render env me set ho to Qwen pehle
# try hota hai, warna Gemini fallback.
QWEN_MODEL = "Qwen/Qwen3-4B"
QWEN_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
QWEN_SYSTEM = (
    "You are RAMA, an intelligent, helpful AI assistant. "
    "Answer accurately in Hindi, English or Hinglish."
)

SYSTEM_PROMPT = (
    "You are Rama, a helpful AI assistant. "
    "Think step by step. "
    "Never invent facts, citations, URLs or statistics. "
    "If you do not know, say so honestly."
)

# Fast mode: seedha, short jawab. Deep mode: step-by-step detail reasoning.
FAST_PROMPT = SYSTEM_PROMPT + " Give a short, direct answer."
DEEP_PROMPT = (
    "You are Rama, a helpful AI assistant. "
    "Think step by step and explain in detail: break the problem into parts, "
    "show your reasoning, then give the final answer with examples where useful. "
    "Never invent facts, citations, URLs or statistics. "
    "If you do not know, say so honestly."
)

# Aise sawal jinhe current/factual info chahiye (web search karo)
FRESH_WORDS = {
    "aaj", "kal", "abhi", "latest", "news", "khabar", "mausam", "weather",
    "price", "rate", "kimat", "bhav", "score", "result", "parinam",
    "kaun", "who", "kab", "when", "kahan", "where", "kitne", "how many",
    "capital", "rajdhani", "population", "aabadi", "president", "pm",
    "today", "current", "live", "abhi ka", "is samay",
}


def _clean_answer(text: str) -> str:
    """HTML entities aur citation markers hatao."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # Qwen thinking block
    text = re.sub(r"&#\w+;", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"\[\d+\]", "", text)  # [1], [12] jaise citations
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_user_name_question(question: str) -> bool:
    """User apna naam poochh raha hai? ("mera naam kya hai" / "what is my name")"""
    low = question.lower()
    return bool(
        re.search(r"mera\s+naa?m\s+kya", low)
        or re.search(r"what\s+is\s+my\s+name", low)
        or re.search(r"what'?s\s+my\s+name", low)
    )


def _is_ai_name_question(question: str) -> bool:
    """AI ka naam poochh raha hai? ("tumhara naam kya hai" / "what is your name")"""
    low = question.lower()
    return bool(
        re.search(r"tumhara\s+naa?m\s+kya", low)
        or re.search(r"aapka\s+naa?m\s+kya", low)
        or re.search(r"what\s+is\s+your\s+name", low)
        or re.search(r"what'?s\s+your\s+name", low)
    )


def _is_greeting(question: str) -> bool:
    """Natural greeting? ("hello" / "hi" / "namaste" — poora message greeting ho)."""
    low = re.sub(r"[^\w\s]", "", question.lower()).strip()
    greetings = {
        "hi", "hii", "hello", "helo", "hey", "hlo",
        "namaste", "namaskar", "namaste ji",
        "good morning", "good afternoon", "good evening",
        "salam", "salaam", "ram ram", "radhe radhe",
    }
    return low in greetings


def _needs_fresh_info(question: str) -> bool:
    """Sawal ko current/factual info chahiye?"""
    low = question.lower()
    words = set(re.findall(r"[a-zA-Z\u0900-\u097F]+", low))
    if words & FRESH_WORDS:
        return True
    if re.search(r"\b(kya hai|what is|who is|kaun hai|capital|rajdhani)\b", low):
        return True
    return False


class AIRouter:
    def __init__(self):
        self._client = None

    def _get_client(self):
        """Gemini client (lazy — key ho to hi banao)."""
        if genai is None:
            return None
        if self._client is None:
            key = get_api_key()
            if not key:
                return None
            try:
                self._client = genai.Client(api_key=key)
            except Exception:
                return None
        return self._client

    def _ask_gemini(self, prompt: str):
        """Gemini se jawab lo; fail ho to None."""
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            text = (resp.text or "").strip()
            return text if text else None
        except Exception:
            return None

    def _ask_qwen(self, prompt: str):
        """Qwen3-4B se jawab lo (HF Inference router); fail ho ya token na ho to None."""
        token = get_hf_token()
        if not token:
            return None
        body = {
            "model": QWEN_MODEL,
            "messages": [
                {"role": "system", "content": QWEN_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.7,
            "top_p": 0.8,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(
            QWEN_ROUTER_URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return text if text else None
        except Exception:
            return None

    def _ask_brain(self, prompt: str):
        """Brain: pehle Qwen3-4B (HF Inference), na chale to Gemini fallback."""
        answer = self._ask_qwen(prompt)
        if answer:
            return answer
        return self._ask_gemini(prompt)

    def answer(self, question: str, db, history=None, mode: str = "fast") -> dict:
        """Sawal ka jawab do -> {answer, sources}. mode: fast | deep."""
        question = (question or "").strip()
        if not question:
            return {"answer": "Kuch poochho to sahi! 😊", "sources": []}
        system_prompt = DEEP_PROMPT if mode == "deep" else FAST_PROMPT

        # 1a. AI ka naam poochh raha hai
        if _is_ai_name_question(question):
            return {"answer": "Main Rama hoon. 😊 Tumhara AI dost!", "sources": []}

        # 1b. User ka naam — memory se, kabhi web search nahi
        if _is_user_name_question(question):
            mem = get_memory(db, "user_name")
            if mem:
                return {"answer": f"Tumhara naam {mem.value} hai. 😊", "sources": []}
            return {
                "answer": "Mujhe tumhara naam abhi pata nahi. Batao — 'mera naam X hai' likh ke yaad kara do!",
                "sources": [],
            }

        # 1c. Natural greeting — friendly reply, no web search, no Gemini
        if _is_greeting(question):
            return {
                "answer": "Hello! 👋 Kaise ho? Batao, main tumhari kya madad kar sakta hoon?",
                "sources": [],
            }

        # 2. Personal memory pehle — >= 2 content words match ho to seedha wahi jawab
        try:
            memories = search_memories(db, question)
        except Exception:
            memories = []
        q_words = set(content_words(question))
        for mem in memories:
            hay_words = set(content_words(f"{mem.key} {mem.value}"))
            overlap = q_words & hay_words
            if len(overlap) >= 2:
                return {"answer": _clean_answer(mem.value), "sources": []}

        # 3. Current/factual sawal — web search
        sources = []
        if _needs_fresh_info(question):
            try:
                results = web_search(question)
            except Exception:
                results = []
            if results:
                sources = results
                web_text = "\n".join(
                    f"- {r.get('title', '')}: {r.get('snippet', '')}" for r in results[:3]
                )
                # Web jawab ko brain se process karwao (saaf, seedha jawab)
                brain_answer = self._ask_brain(
                    f"{system_prompt}\n\n"
                    f"Search results:\n{web_text}\n\n"
                    f"Question: {question}\n\n"
                    "Answer ONLY from the search results above. "
                    "If the search results do not contain the answer, say you don't know."
                )
                if brain_answer:
                    return {"answer": _clean_answer(brain_answer), "sources": sources}
                # Brain nahi chala to seedha web snippet do
                first = results[0].get("snippet", "").strip()
                if first:
                    return {"answer": _clean_answer(first), "sources": sources}

        # 4. Warna brain se jawab (Qwen pehle, Gemini fallback)
        history_text = ""
        if history:
            try:
                lines = []
                for h in history[-6:]:
                    role = h.get("role", "user")
                    content = h.get("content", "")
                    lines.append(f"{role}: {content}")
                history_text = "\n".join(lines)
            except Exception:
                history_text = ""
        prompt = system_prompt + "\n\n"
        if history_text:
            prompt += f"Conversation so far:\n{history_text}\n\n"
        prompt += (
            f"Question: {question}\n\n"
            "Answer in the same language as the question (Hindi/Hinglish/English)."
        )
        brain_answer = self._ask_brain(prompt)
        if brain_answer:
            return {"answer": _clean_answer(brain_answer), "sources": sources}

        # 5. Last fallback — web search ya imaandaar "nahi pata"
        if not sources:
            try:
                sources = web_search(question)
            except Exception:
                sources = []
        if sources:
            first = sources[0].get("snippet", "").strip()
            if first:
                return {"answer": _clean_answer(first), "sources": sources}
        return {
            "answer": "Mujhe iska sahi jawab nahi pata. Dobara poochho ya kuch aur poochho!",
            "sources": [],
        }
