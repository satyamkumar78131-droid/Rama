
"""
RAMA AI ROUTER — COMPLETE UPGRADED VERSION
==========================================

Features:
1. RAMA AI name detection
2. User name detection from memory
3. Personal memory search
4. Current information via web search
5. Gemini 3.8 Flash primary model
6. Gemini 3.5 Flash-Lite backup model
7. Automatic retry and error handling
8. Fast and Deep modes
9. Hindi, Hinglish and English
10. Conversation history
11. Natural greeting responses
12. Detailed error logging
13. Safe fallback responses
14. HTML entity and citation cleanup
"""

import re
import time
import logging

# =====================================================
# LOGGING
# =====================================================

logger = logging.getLogger("rama.ai")

# =====================================================
# GEMINI SDK
# =====================================================

try:
    from google import genai
except Exception:
    genai = None

# =====================================================
# INTERNAL MODULES
# =====================================================

from memory import (
    content_words,
    get_memory,
    search_memories
)

from security import get_api_key
from web_search import web_search

# =====================================================
# MODEL CONFIGURATION
# =====================================================

MODEL = "gemini-3.8-flash"

FALLBACK_MODEL = "gemini-3.5-flash-lite"

MAX_RETRIES = 2

RETRY_DELAY = 1.5

# Temporary errors that may succeed on retry
RETRYABLE_ERRORS = {
    429,
    500,
    502,
    503,
    504
}

# =====================================================
# SYSTEM PROMPTS
# =====================================================

SYSTEM_PROMPT = """
You are RAMA, a helpful personal AI assistant.

PERSONALITY:
- Friendly, intelligent and professional.
- Speak naturally and conversationally.
- Support Hindi, Hinglish and English.
- Understand conversation context.
- Give accurate and useful answers.
- Never invent facts, sources or statistics.
- If you do not know, say so honestly.
- Avoid unnecessary introductions.
- Do not introduce yourself unless asked.
- Answer greetings naturally.
- Keep simple answers short.
- Use clear formatting when helpful.

ACCURACY:
- Never pretend to have searched the web.
- Never invent URLs or citations.
- Distinguish facts from uncertainty.
- Correct mistakes when identified.
- Use conversation history when relevant.
"""

FAST_PROMPT = SYSTEM_PROMPT + """

FAST MODE:
- Give direct and concise answers.
- Avoid unnecessary explanations.
- Prioritize useful information.
- Use simple language.
"""

DEEP_PROMPT = SYSTEM_PROMPT + """

DEEP MODE:
- Analyze the question carefully.
- Explain important steps and concepts.
- Provide examples where useful.
- Organize answers using headings.
- Explain conclusions clearly.
- Do not reveal private internal reasoning.
"""

# =====================================================
# CURRENT INFORMATION KEYWORDS
# =====================================================

FRESH_WORDS = {
    "aaj",
    "kal",
    "abhi",
    "latest",
    "news",
    "khabar",
    "mausam",
    "weather",
    "price",
    "rate",
    "kimat",
    "bhav",
    "score",
    "result",
    "parinam",
    "kab",
    "when",
    "kahan",
    "where",
    "kitne",
    "capital",
    "rajdhani",
    "population",
    "aabadi",
    "president",
    "pm",
    "today",
    "current",
    "live",
    "is samay",
    "latest update",
    "election",
    "stock",
    "share price"
}

# =====================================================
# TEXT CLEANER
# =====================================================

def _clean_answer(text: str) -> str:

    if not text:
        return ""

    text = str(text)

    # HTML entities
    text = re.sub(
        r"&#(?:x[0-9a-fA-F]+|\d+);",
        "",
        text
    )

    replacements = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&nbsp;": " "
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Citation markers
    text = re.sub(
        r"\[\d+\]",
        "",
        text
    )

    # Excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# =====================================================
# NAME DETECTION
# =====================================================

def _is_user_name_question(question: str) -> bool:

    low = question.lower().strip()

    patterns = [
        r"mera\s+naa?m\s+kya",
        r"what\s+is\s+my\s+name",
        r"what'?s\s+my\s+name",
        r"do\s+you\s+know\s+my\s+name"
    ]

    return any(
        re.search(pattern, low)
        for pattern in patterns
    )


def _is_ai_name_question(question: str) -> bool:

    low = question.lower().strip()

    patterns = [
        r"tumhara\s+naa?m\s+kya",
        r"aapka\s+naa?m\s+kya",
        r"what\s+is\s+your\s+name",
        r"what'?s\s+your\s+name",
        r"who\s+are\s+you",
        r"tum\s+kon\s+ho",
        r"tum\s+kaun\s+ho",
        r"aap\s+kaun\s+hain",
        r"your\s+name"
    ]

    return any(
        re.search(pattern, low)
        for pattern in patterns
    )


# =====================================================
# GREETING DETECTION
# =====================================================

def _is_greeting(question: str) -> bool:

    low = re.sub(
        r"[^\w\s]",
        "",
        question.lower()
    ).strip()

    greetings = {
        "hi",
        "hii",
        "hello",
        "helo",
        "hey",
        "hlo",
        "namaste",
        "namaskar",
        "good morning",
        "good afternoon",
        "good evening",
        "salam"
    }

    return low in greetings


# =====================================================
# FRESH INFORMATION DETECTION
# =====================================================

def _needs_fresh_info(question: str) -> bool:

    low = question.lower()

    words = set(
        re.findall(
            r"[a-zA-Z\u0900-\u097F]+",
            low
        )
    )

    if words & FRESH_WORDS:
        return True

    patterns = [
        r"\bkya hai\b",
        r"\bwhat is\b",
        r"\bwho is\b",
        r"\bwho was\b",
        r"\bkaun hai\b",
        r"\bkaun tha\b",
        r"\bhow many\b",
        r"\bhow much\b",
        r"\bcapital\b",
        r"\brajdhani\b",
        r"\bkitna hai\b",
        r"\bkitni hai\b"
    ]

    return any(
        re.search(pattern, low)
        for pattern in patterns
    )


# =====================================================
# MAIN AI ROUTER
# =====================================================

class AIRouter:

    def __init__(self):

        self._client = None

        logger.info(
            "RAMA AI Router initialized."
        )

    # =================================================
    # GEMINI CLIENT
    # =================================================

    def _get_client(self):

        if genai is None:

            logger.error(
                "Google GenAI SDK is missing."
            )

            return None

        if self._client is None:

            try:

                key = get_api_key()

                if not key:

                    logger.error(
                        "GEMINI_API_KEY is missing or empty."
                    )

                    return None

                self._client = genai.Client(
                    api_key=key
                )

                logger.info(
                    "Gemini client initialized."
                )

            except Exception:

                logger.exception(
                    "Gemini client initialization failed."
                )

                return None

        return self._client

    # =================================================
    # EXTRACT ERROR STATUS
    # =================================================

    def _get_error_status(self, exc):

        status = (
            getattr(exc, "code", None)
            or getattr(exc, "status_code", None)
        )

        try:

            if status is not None:
                return int(status)

        except (TypeError, ValueError):
            pass

        message = str(exc)

        match = re.search(
            r"\b(400|401|403|404|408|429|500|502|503|504)\b",
            message
        )

        if match:
            return int(match.group(1))

        return None

    # =================================================
    # GEMINI REQUEST WITH RETRY + BACKUP
    # =================================================

    def _ask_gemini(self, prompt: str):

        client = self._get_client()

        if client is None:
            return None

        models = [
            MODEL,
            FALLBACK_MODEL
        ]

        for model in models:

            for attempt in range(MAX_RETRIES):

                try:

                    logger.info(
                        "Requesting Gemini model: %s",
                        model
                    )

                    response = client.models.generate_content(
                        model=model,
                        contents=prompt
                    )

                    answer = (
                        response.text or ""
                    ).strip()

                    if answer:

                        logger.info(
                            "Gemini response successful: %s",
                            model
                        )

                        return answer

                    logger.warning(
                        "Gemini returned empty response: %s",
                        model
                    )

                    break

                except Exception as exc:

                    status = self._get_error_status(
                        exc
                    )

                    logger.warning(
                        "Gemini request failed. "
                        "Model=%s Status=%s Attempt=%s Error=%s",
                        model,
                        status,
                        attempt + 1,
                        str(exc)
                    )

                    # Authentication errors cannot be fixed
                    # by switching models.
                    if status in (400, 401, 403):
                        return None

                    # Retry temporary errors
                    if (
                        status in RETRYABLE_ERRORS
                        and attempt < MAX_RETRIES - 1
                    ):

                        delay = (
                            RETRY_DELAY * (2 ** attempt)
                        )

                        logger.info(
                            "Retrying %s after %.1f seconds.",
                            model,
                            delay
                        )

                        time.sleep(delay)

                        continue

                    # Try backup model
                    break

        logger.error(
            "Primary and backup Gemini models failed."
        )

        return None

    # =================================================
    # WEB SEARCH
    # =================================================

    def _search_web(self, question: str):

        try:

            results = web_search(question)

            if not results:
                return []

            if not isinstance(results, list):
                return []

            return results

        except Exception:

            logger.exception(
                "Web search failed."
            )

            return []

    # =================================================
    # PREPARE WEB CONTEXT
    # =================================================

    def _prepare_web_context(self, sources):

        lines = []

        for result in sources[:5]:

            if not isinstance(result, dict):
                continue

            title = result.get(
                "title",
                ""
            )

            snippet = result.get(
                "snippet",
                ""
            )

            if title or snippet:

                lines.append(
                    f"- {title}: {snippet}"
                )

        return "\n".join(lines)

    # =================================================
    # CONVERSATION HISTORY
    # =================================================

    def _prepare_history(self, history, question):

        if not history:
            return ""

        try:

            lines = []

            items = history[-10:]

            # main.py may already include the current message
            # in history. Avoid adding it twice.
            if items:

                last = items[-1]

                if (
                    last.get("role") == "user"
                    and last.get("content", "").strip() == question
                ):
                    items = items[:-1]

            for item in items:

                role = item.get(
                    "role",
                    "user"
                )

                content = item.get(
                    "content",
                    ""
                )

                if not content:
                    continue

                if role not in ("user", "assistant"):
                    continue

                lines.append(
                    f"{role}: {content}"
                )

            return "\n".join(lines)

        except Exception:

            logger.exception(
                "Conversation history processing failed."
            )

            return ""

    # =================================================
    # MAIN ANSWER FUNCTION
    # =================================================

    def answer(
        self,
        question: str,
        db,
        history=None,
        mode: str = "fast"
    ) -> dict:

        question = (
            question or ""
        ).strip()

        if not question:

            return {
                "answer": "Kuch poochho to sahi! 😊",
                "sources": []
            }

        mode = (
            mode or "fast"
        ).lower()

        if mode not in ("fast", "deep"):
            mode = "fast"

        system_prompt = (
            DEEP_PROMPT
            if mode == "deep"
            else FAST_PROMPT
        )

        logger.info(
            "New request received. Mode=%s",
            mode
        )

        # =============================================
        # 1. AI NAME
        # =============================================

        if _is_ai_name_question(question):

            return {
                "answer": (
                    "Main RAMA hoon! 😊 "
                    "Tumhara personal AI assistant."
                ),
                "sources": [],
                "mode": mode
            }

        # =============================================
        # 2. USER NAME
        # =============================================

        if _is_user_name_question(question):

            try:

                mem = get_memory(
                    db,
                    "user_name"
                )

                if mem:

                    return {
                        "answer": (
                            f"Tumhara naam {mem.value} hai. 😊"
                        ),
                        "sources": [],
                        "mode": mode
                    }

            except Exception:

                logger.exception(
                    "User name memory lookup failed."
                )

            return {
                "answer": (
                    "Mujhe tumhara naam abhi pata nahi. "
                    "Batao: 'mera naam X hai' likhkar yaad kara do!"
                ),
                "sources": [],
                "mode": mode
            }

        # =============================================
        # 3. NATURAL GREETINGS
        # =============================================

        if _is_greeting(question):

            return {
                "answer": (
                    "Hello! 👋 Kaise ho? "
                    "Batao, main tumhari kya madad kar sakta hoon?"
                ),
                "sources": [],
                "mode": mode
            }

        # =============================================
        # 4. PERSONAL MEMORY
        # =============================================

        try:

            memories = search_memories(
                db,
                question
            )

        except Exception:

            logger.exception(
                "Personal memory search failed."
            )

            memories = []

        try:

            q_words = set(
                content_words(question)
            )

            for mem in memories:

                hay_words = set(
                    content_words(
                        f"{mem.key} {mem.value}"
                    )
                )

                overlap = q_words & hay_words

                if len(overlap) >= 2:

                    logger.info(
                        "Answer retrieved from personal memory."
                    )

                    return {
                        "answer": _clean_answer(
                            mem.value
                        ),
                        "sources": [],
                        "mode": mode
                    }

        except Exception:

            logger.exception(
                "Memory matching failed."
            )

        # =============================================
        # 5. CURRENT INFORMATION / WEB SEARCH
        # =============================================

        sources = []

        needs_fresh = _needs_fresh_info(
            question
        )

        if needs_fresh:

            sources = self._search_web(
                question
            )

            if sources:

                web_context = (
                    self._prepare_web_context(
                        sources
                    )
                )

                if web_context:

                    web_prompt = (
                        f"{system_prompt}\n\n"
                        "You are answering using web search results.\n"
                        "Use only the supplied search information.\n"
                        "Do not invent missing facts.\n"
                        "If information is insufficient, clearly say so.\n\n"
                        f"Search results:\n{web_context}\n\n"
                        f"Question: {question}\n\n"
                        "Answer in the same language as the user."
                    )

                    gemini_answer = self._ask_gemini(
                        web_prompt
                    )

                    if gemini_answer:

                        return {
                            "answer": _clean_answer(
                                gemini_answer
                            ),
                            "sources": sources,
                            "mode": mode
                        }

                # Gemini unavailable:
                # use available search snippet.

                first = (
                    sources[0].get(
                        "snippet",
                        ""
                    ).strip()
                    if isinstance(sources[0], dict)
                    else ""
                )

                if first:

                    logger.warning(
                        "Using web snippet fallback."
                    )

                    return {
                        "answer": _clean_answer(first),
                        "sources": sources,
                        "mode": mode
                    }

        # =============================================
        # 6. CONVERSATION HISTORY
        # ============================================