
"""RAMA — Intelligent AI Router V2
Smart conversation, identity, memory, web search and Gemini.
"""

import re
from urllib.parse import urlparse

try:
    from google import genai
except Exception:
    genai = None

from memory import content_words, get_memory, search_memories
from security import get_api_key
from web_search import web_search

MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """
You are RAMA, a helpful, friendly and intelligent AI assistant.

Your identity:
- Your name is RAMA.
- If asked who you are, say you are RAMA.
- Never claim to be another AI.

Rules:
- Answer in the same language as the user.
- Understand Hindi, Hinglish and English.
- Be natural and conversational.
- Never invent facts, sources or URLs.
- Use conversation history when relevant.
- If you don't know something, say so honestly.
- Give clear and useful answers.
- Do not output HTML entities or fake citations.
"""

FAST_PROMPT = SYSTEM_PROMPT + """
Keep answers concise, direct and useful.
"""

DEEP_PROMPT = SYSTEM_PROMPT + """
Give detailed, well-structured explanations.
Explain important steps and conclusions without exposing private
internal reasoning.
Use examples when helpful.
"""

# Only explicit current-information signals trigger web search.
FRESH_WORDS = {
    "latest", "today", "tonight", "yesterday",
    "breaking", "news", "headlines",
    "current", "currently", "live", "real-time",
    "weather", "forecast", "temperature",
    "price", "prices", "stock", "market",
    "score", "scores", "match", "standings",
    "election", "result", "results",
    "mausam", "aaj", "abhi", "taaza",
    "khabar", "samachar", "bhav", "kimat",
    "rate", "dar", "live-score",
}

def _clean_answer(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"&#\w+;", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _is_greeting(question):
    q = _normalize(question)

    patterns = [
        r"^(hi|hello|hey|hii|heyy)[!. ]*$",
        r"^(namaste|namaskar|pranam)[!. ]*$",
        r"^(good morning|good afternoon|good evening)[!. ]*$",
        r"^(kaise ho|kaisa hai|kaisi ho)[?!. ]*$",
        r"^(how are you|how are you doing)[?!. ]*$",
        r"^(kya haal hai|sab badhiya|aur batao)[?!. ]*$",
    ]

    return any(re.match(p, q) for p in patterns)


def _is_ai_name_question(question):
    q = _normalize(question)

    patterns = [
        r"\b(tumhara|aapka|tera)\s+naam\s+kya\b",
        r"\b(what is|what's)\s+your\s+name\b",
        r"\bwho\s+are\s+you\b",
        r"\btum\s+kaun\s+ho\b",
        r"\btum\s+kon\s+ho\b",
        r"\baap\s+kaun\s+ho\b",
        r"\baap\s+kon\s+ho\b",
        r"\btera\s+naam\s+kya\s+hai\b",
    ]

    return any(re.search(p, q) for p in patterns)


def _is_user_name_question(question):
    q = _normalize(question)

    patterns = [
        r"\bmera\s+naam\s+kya\b",
        r"\bwhat is my name\b",
        r"\bwhat's my name\b",
        r"\bdo you know my name\b",
    ]

    return any(re.search(p, q) for p in patterns)


def _needs_fresh_info(question):
    q = _normalize(question)
    words = set(re.findall(r"[a-zA-Z\u0900-\u097F]+", q))

    # Explicit fresh-information keywords
    if words & FRESH_WORDS:
        return True

    # Explicit current-information requests
    patterns = [
        r"\b(latest|recent|breaking)\s+(news|updates|information)\b",
        r"\bwhat happened (today|yesterday|recently)\b",
        r"\bwho is the current\b",
        r"\bcurrent (president|prime minister|pm|ceo)\b",
        r"\b(aaj ki|taaza)\s+(khabar|news)\b",
        r"\b(abhi ka|aaj ka)\s+(price|rate|score|result)\b",
        r"\bprice of\b.*\b(today|now|current)\b",
    ]

    return any(re.search(p, q) for p in patterns)


def _dedupe_sources(sources):
    """Remove duplicate URLs and repeated source domains."""
    unique = []
    seen_urls = set()
    seen_domains = set()

    for source in sources or []:
        if not isinstance(source, dict):
            continue

        url = (
            source.get("url")
            or source.get("link")
            or source.get("href")
            or ""
        )

        domain = ""
        if url:
            try:
                domain = urlparse(url).netloc.lower()
                domain = domain.removeprefix("www.")
            except Exception:
                domain = ""

        if url and url in seen_urls:
            continue

        if domain and domain in seen_domains:
            continue

        if url:
            seen_urls.add(url)

        if domain:
            seen_domains.add(domain)

        unique.append(source)

        if len(unique) >= 5:
            break

    return unique


class AIRouter:

    def __init__(self):
        self._client = None

    def _get_client(self):
        if genai is None:
            return None

        if self._client is None:
            try:
                key = get_api_key()
                if not key:
                    return None

                self._client = genai.Client(api_key=key)

            except Exception:
                return None

        return self._client

    def _ask_gemini(self, prompt):
        client = self._get_client()

        if client is None:
            return None

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )

            answer = getattr(response, "text", None)

            if answer:
                return _clean_answer(answer)

        except Exception:
            return None

        return None

    def _search(self, question):
        try:
            results = web_search(question)
            return _dedupe_sources(results)
        except Exception:
            return []

    def answer(self, question, db, history=None, mode="fast"):

        question = (question or "").strip()

        if not question:
            return {
                "answer": "Kuch poochho to sahi! 😊",
                "sources": [],
            }

        mode = (mode or "fast").lower()

        system_prompt = (
            DEEP_PROMPT if mode == "deep"
            else FAST_PROMPT
        )

        # 1. RAMA identity
        if _is_ai_name_question(question):
            return {
                "answer": "Main RAMA hoon! 😊 Tumhara personal AI assistant.",
                "sources": [],
            }

        # 2. User identity
        if _is_user_name_question(question):
            try:
                mem = get_memory(db, "user_name")

                if mem:
                    return {
                        "answer": f"Tumhara naam {mem.value} hai. 😊",
                        "sources": [],
                    }

            except Exception:
                pass

            return {
                "answer": (
                    "Mujhe abhi tumhara naam nahi pata. "
                    "Apna naam bata do, main yaad rakhne ki koshish karunga."
                ),
                "sources": [],
            }

        # 3. Greetings and small talk
        if _is_greeting(question):
            q = _normalize(question)

            if "how are you" in q or "kaise ho" in q or "kaisa hai" in q:
                answer = (
                    "Main badhiya hoon! 😊 "
                    "Tum batao, main tumhari kya help kar sakta hoon?"
                )
            elif "good morning" in q:
                answer = "Good morning! ☀️ Aaj main tumhari kya help karun?"
            elif "good evening" in q:
                answer = "Good evening! 😊 Kaise ho?"
            elif "good afternoon" in q:
                answer = "Good afternoon! 😊 Batao, kya help chahiye?"
            else:
                answer = (
                    "Hello! 👋 Main RAMA hoon. "
                    "Batao, aaj kya jaanna chahte ho?"
                )

            return {
                "answer": answer,
                "sources": [],
            }

        # 4. Personal memory first
        try:
            memories = search_memories(db, question)
        except Exception:
            memories = []

        q_words = set(content_words(question))

        for mem in memories:
            try:
                saved_words = set(
                    content_words(f"{mem.key} {mem.value}")
                )

                if len(q_words & saved_words) >= 2:
                    return {
                        "answer": _clean_answer(mem.value),
                        "sources": [],
                    }

            except Exception:
                continue

        # 5. Recent/current information only
        sources = []

        if _needs_fresh_info(question):
            sources = self._search(question)

            if sources:
                web_text = "\n".join(
                    f"- {r.get('title', '')}: {r.get('snippet', '')}"
                    for r in sources[:5]
                )

                prompt = (
                    system_prompt
                    + "\n\nUse ONLY these search results for current facts.\n"
                    + web_text
                    + f"\n\nUser question: {question}\n"
                    + "Answer naturally in the user's language. "
                    + "If the results do not answer the question, "
                    + "clearly say that the information is unavailable."
                )

                answer = self._ask_gemini(prompt)

                if answer:
                    return {
                        "answer": answer,
                        "sources": sources,
                    }

                # Gemini unavailable: use actual search snippets
                snippets = [
                    r.get("snippet", "").strip()
                    for r in sources
                    if r.get("snippet", "").strip()
                ]

                if snippets:
                    return {
                        "answer": _clean_answer(snippets[0]),
                        "sources": sources,
                    }

        # 6. Normal conversation with history
        history_text = ""

        if history:
            try:
                lines = []

                for item in history[-8:]:
                    role = item.get("role", "user")
                    content = item.get("content", "")

                    if role not in ("user", "assistant"):
                        continue

                    lines.append(f"{role}: {content}")

                history_text = "\n".join(lines)

            except Exception:
                history_text = ""

        prompt = system_prompt + "\n\n"

        if history_text:
            prompt += (
                "Previous conversation:\n"
                + history_text
                + "\n\n"
            )

        prompt += (
            f"User: {question}\n\n"
            "Respond naturally and directly. "
            "Do not search the internet for ordinary conversation. "
            "Answer in the same language as the user."
        )

        answer = self._ask_gemini(prompt)

        if answer:
            return {
                "answer": answer,
                "sources": [],
            }

        # 7. Honest fallback — NEVER search every failed chat question
        return {
            "answer": (
                "Abhi mera AI service respond nahi kar raha. "
                "Thodi der baad dobara try karo. 😊"
            ),
            "sources": [],
        }
