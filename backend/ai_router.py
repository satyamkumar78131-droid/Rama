"""Rama — AI router (SAIME wala proven flow).

Order (hamesha yahi):
1. Naam wale sawal — "tumhara naam kya hai" -> "Main Rama hoon";
   "mera naam kya hai" -> user_name memory se. Kabhi web search nahi.
2. Personal memory pehle — saved memory jawab de (>= 2 content words
   overlap) to web search BILKUL nahi.
3. Current/factual sawal — web_search + sources.
4. Warna BRAIN se jawab — pehle Qwen3.8-27B (Groq free tier), na chale to
   Gemini fallback (models ek ke baad ek try hote hain: 3.8 Flash, phir
   3.5 Flash-Lite, phir 2.5 Flash — jo mile wahi). Step by step, facts
   invent nahi karta.
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
    from google.genai import types
except Exception:  # google-genai install na ho to bhi app chalegi
    genai = None
    types = None

from memory import content_words, get_memory, search_memories
from security import get_api_key, get_groq_token, get_hf_token
from web_search import web_search

# Gemini models, try karne ka order. gemini-2.0-flash band ho gaya hai
# ("no longer available") — isliye naye models pehle; jo mile wahi use hoga.
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]

# Qwen brain — Groq free tier (OpenAI-compatible). Koi nayi dependency
# nahi — sirf stdlib urllib. GROQ_API_KEY Render env me set ho to Qwen
# pehle try hota hai, warna Gemini fallback.
# NOTE: HF Inference PAUSED hai — HF account me inference credits $0 hain,
# isliye HF router hamesha HTTP 400 deta hai ("not supported by any provider
# you have enabled"). Qwen ab Groq se chalega.
# Groq pe Qwen3-32B band ho gaya (July 2026) — isliye qwen3.8-27b use ho raha hai.
QWEN_MODEL = "qwen/qwen3.8-27b"
QWEN_ROUTER_URL = "https://api.groq.com/openai/v1/chat/completions"
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
    """AI ka naam/pehchan poochh raha hai? ("tumhara naam kya hai" / "what is your name" / "who are you")"""
    low = question.lower()
    return bool(
        re.search(r"tumhara\s+naa?m\s+kya", low)
        or re.search(r"aapka\s+naa?m\s+kya", low)
        or re.search(r"what\s+is\s+your\s+name", low)
        or re.search(r"what'?s\s+your\s+name", low)
        # "who are you" — sirf jab uske baad sawal khatm ho (punctuation/end),
        # warna "who are you talking about" galat pakda jayega
        or re.search(r"who\s+are\s+you\s*(?:[?.!]|$)", low)
        or re.search(r"\bwho\s+r\s+(u|you)\b", low)
        or re.search(r"what\s+are\s+you\s*(?:[?.!]|$)", low)
        or re.search(r"introduce\s+yourself\b", low)
        or re.search(r"tum\s+kaun\s+(ho|hai|hain)\b", low)
        or re.search(r"aap\s+kaun\s+(ho|hain)\b", low)
        or re.search(r"tu\s+kaun\s+hai\b", low)
        or re.search(r"tum\s+kya\s+ho\s*(?:[?.!]|$)", low)
        or re.search(r"apna\s+naam\s+batao\b", low)
    )


def _is_creator_question(question: str) -> bool:
    """RAMA ko kisne banaya — ye sawal? ("tumhe kisne banaya" / "who made you")
    Dhyaan: "Taj Mahal kisne banaya" / "Python kisne banaya" isme NAHI aane chahiye —
    isliye 'tumhe/tumko/aapko' ya 'you' ka hona zaroori hai."""
    low = question.lower()
    return bool(
        re.search(r"(tumhe|tumko|tujhe|aapko)\s+(kisne|kis\s+ne)\s+banaya", low)
        or re.search(r"kisne\s+banaya\s+(tumhe|tumko|tujhe|aapko)", low)
        or re.search(r"(tumhe|tumko|tujhe|aapko)\s+kisne\s+(develop|create|design)\s+kiya", low)
        or re.search(r"who\s+(made|created|built|developed|designed)\s+you\b", low)
        or re.search(r"who\s+is\s+your\s+(creator|developer|maker)\b", low)
        or re.search(r"\bwho\s+made\s+u\b", low)
        or re.search(r"tumhara\s+(creator|developer)\b", low)
        or re.search(r"tum\s+kisne\s+banaya", low)
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
        self._last_qwen_error = None
        self._last_gemini_error = None

    @staticmethod
    def _safe_err(e):
        """Error ko chhota + safe rakho — token/key kabhi isme na aaye."""
        s = str(e)[:120]
        for secret in (get_api_key(), get_hf_token(), get_groq_token()):
            if secret:
                s = s.replace(secret, "***")
        return s or type(e).__name__

    def _get_client(self):
        """Gemini client (lazy — key ho to hi banao)."""
        if genai is None:
            self._last_gemini_error = "no genai lib"
            return None
        if self._client is None:
            key = get_api_key()
            if not key:
                self._last_gemini_error = "no key"
                return None
            try:
                self._client = genai.Client(api_key=key)
            except Exception as e:
                self._last_gemini_error = self._safe_err(e)
                return None
        return self._client

    def _ask_gemini(self, prompt: str):
        """Gemini se jawab lo (models ek ke baad ek try hote hain);
        sab fail hon to None (wajah _last_gemini_error me)."""
        client = self._get_client()
        if client is None:
            return None
        last_err = None
        for model in GEMINI_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                text = (resp.text or "").strip()
                if text:
                    self._last_gemini_error = None
                    return text
                last_err = "empty response"
            except Exception as e:
                last_err = self._safe_err(e)
        self._last_gemini_error = last_err
        return None

    def describe_image(self, data: bytes, mime: str):
        """Photo ko Gemini se describe karwao (vision — Qwen text-only hai);
        fail ho to None (wajah _last_gemini_error me)."""
        client = self._get_client()
        if client is None or types is None:
            return None
        last_err = None
        for model in GEMINI_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=data, mime_type=mime),
                        "Is photo ko detail me describe karo — Hindi/Hinglish me, "
                        "ek friendly assistant ki tarah. Photo me kya dikh raha hai, "
                        "kaun/kaise log ya cheezein hain, aur mahaul kaisa hai — sab batao.",
                    ],
                )
                text = (resp.text or "").strip()
                if text:
                    self._last_gemini_error = None
                    return text
                last_err = "empty response"
            except Exception as e:
                last_err = self._safe_err(e)
        self._last_gemini_error = last_err
        return None

    def _ask_qwen(self, prompt: str):
        """Qwen3.8-27B se jawab lo (Groq free tier); fail ho ya token na ho to None
        (wajah _last_qwen_error me)."""
        token = get_groq_token()
        if not token:
            self._last_qwen_error = "no token"
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
            # NOTE: Groq ko "provider" field nahi chahiye (HF router wala field
            # tha). Qwen3.8-27B thinking model hai — <think> block aaye to
            # _clean_answer use hata deta hai.
        }
        req = urllib.request.Request(
            QWEN_ROUTER_URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # NOTE: Groq Cloudflare ke peeche hai — Python-urllib ka default
                # User-Agent 403 (error 1010) deta hai, isliye apna UA bhejte hain.
                "User-Agent": "RAMA/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            text = (data["choices"][0]["message"]["content"] or "").strip()
            if text:
                self._last_qwen_error = None
                return text
            self._last_qwen_error = "empty response"
            return None
        except urllib.error.HTTPError as e:
            # Groq ka error body (jaise {"error": "..."}) — asli wajah isme hoti hai
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                detail = ""
            self._last_qwen_error = self._safe_err(
                f"HTTP Error {e.code}: {detail or e.reason}"
            )
            return None
        except Exception as e:
            self._last_qwen_error = self._safe_err(e)
            return None

    def _ask_brain(self, prompt: str):
        """Brain: pehle Qwen3.8-27B (Groq free tier), na chale to Gemini fallback.
        Returns (answer, brain) — brain: 'qwen' | 'gemini' | None."""
        answer = self._ask_qwen(prompt)
        if answer:
            return answer, "qwen"
        answer = self._ask_gemini(prompt)
        if answer:
            return answer, "gemini"
        return None, None

    def answer(self, question: str, db, history=None, mode: str = "fast") -> dict:
        """Sawal ka jawab do -> {answer, sources}. mode: fast | deep."""
        question = (question or "").strip()
        if not question:
            return {"answer": "Kuch poochho to sahi! 😊", "sources": []}
        system_prompt = DEEP_PROMPT if mode == "deep" else FAST_PROMPT

        # 1a. AI ka naam poochh raha hai
        if _is_ai_name_question(question):
            return {"answer": "Main Rama hoon. 😊 Tumhara AI dost!", "sources": []}

        # 1a2. RAMA ko kisne banaya — fixed jawab, warna Qwen/Gemini alag-alag batate hain
        if _is_creator_question(question):
            return {"answer": "Mujhe Satya ne banaya hai — main RAMA, unka AI assistant hoon. 😊", "sources": []}

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
                brain_answer, brain = self._ask_brain(
                    f"{system_prompt}\n\n"
                    f"Search results:\n{web_text}\n\n"
                    f"Question: {question}\n\n"
                    "Answer ONLY from the search results above. "
                    "If the search results do not contain the answer, say you don't know."
                )
                if brain_answer:
                    out = {"answer": _clean_answer(brain_answer), "sources": sources, "brain": brain}
                    if brain == "gemini" and self._last_qwen_error:
                        out["debug"] = {"qwen": self._last_qwen_error}
                    return out
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
        brain_answer, brain = self._ask_brain(prompt)
        if brain_answer:
            out = {"answer": _clean_answer(brain_answer), "sources": sources, "brain": brain}
            # Gemini se jawab aaya matlab Qwen fail hua — uski wajah bhi dikhao
            if brain == "gemini" and self._last_qwen_error:
                out["debug"] = {"qwen": self._last_qwen_error}
            return out

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
            "debug": {"qwen": self._last_qwen_error, "gemini": self._last_gemini_error},
        }
