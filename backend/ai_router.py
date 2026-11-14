
"""
RAMA AI ROUTER — Updated Version
--------------------------------
1. AI name detection
2. Personal memory
3. Current information via web search
4. Gemini 3.8 Flash for normal conversation
5. Detailed error logging
6. Fast and Deep modes
7. Hindi, Hinglish and English
"""

import re
import logging

logger = logging.getLogger("rama.ai")

# Gemini SDK
try:
    from google import genai
except Exception:
    genai = None

from memory import content_words, get_memory, search_memories
from security import get_api_key
from web_search import web_search


# Current Gemini model
MODEL = "gemini-3.8-flash"


# SYSTEM PROMPTS
SYSTEM_PROMPT = """
You are RAMA, a helpful personal AI assistant.

Your personality:
- Friendly, intelligent and professional.
- Speak naturally like a real conversational assistant.
- Support Hindi, Hinglish and English.
- Understand context and previous messages.
- Give accurate and useful answers.
- Never invent facts, sources or statistics.
- If you do not know something, say so honestly.
- Avoid unnecessary introductions.
- Answer greetings naturally.
- Keep simple answers short.
"""

FAST_PROMPT = SYSTEM_PROMPT + """
FAST MODE:
Give direct, concise and useful answers.
Avoid unnecessary explanations.
"""

DEEP_PROMPT = SYSTEM_PROMPT + """
DEEP MODE:
Analyze the question carefully.
Explain the important steps and concepts.
Give examples when useful.
Provide a detailed and organized answer.
Do not expose private internal reasoning.
"""


# Current information keywords
FRESH_WORDS = {
    "aaj", "kal", "abhi", "latest", "news", "khabar",
    "mausam", "weather", "price", "rate", "kimat",
    "bhav", "score", "result", "parinam",
    "kab", "when", "kahan", "where", "kitne",
    "how many", "capital", "rajdhani",
    "population", "aabadi", "president",
    "pm", "today", "current", "live",
    "is samay"
}


# CLEAN ANSWER
def _clean_answer(text: str) -> str:

    if not text:
        return ""

    text = re.sub(r"&#\w+;", "", text)

    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")

    # Remove citation markers
    text = re.sub(r"\[\d+\]", "", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# NAME DETECTION
def _is_user_name_question(question: str) -> bool:

    low = question.lower()

    patterns = [
        r"mera\s+naa?m\s+kya",
        r"what\s+is\s+my\s+name",
        r"what'?s\s+my\s+name"
    ]

    return any(re.search(p, low) for p in patterns)


def _is_ai_name_question(question: str) -> bool:

    low = question.lower()

    patterns = [
        r"tumhara\s+naa?m\s+kya",
        r"aapka\s+naa?m\s+kya",
        r"what\s+is\s+your\s+name",
        r"what'?s\s+your\s+name",
        r"who\s+are\s+you",
        r"tum\s+kon\s+ho",
        r"tum\s+kaun\s+ho",
        r"aap\s+kaun\s+hain"
    ]

    return any(re.search(p, low) for p in patterns)


# FRESH INFORMATION DETECTION
def _needs_fresh_info(question: str) -> bool:

    low = question.lower()

    words = set(
        re.findall(r"[a-zA-Z\u0900-\u097F]+", low)
    )

    if words & FRESH_WORDS:
        return True

    patterns = [
        r"\bkya hai\b",
        r"\bwhat is\b",
        r"\bwho is\b",
        r"\bkaun hai\b",
        r"\bcapital\b",
        r"\brajdhani\b"
    ]

    return any(re.search(p, low) for p in patterns)


# MAIN AI ROUTER
class AIRouter:

    def __init__(self):
        self._client = None

    # GEMINI CLIENT
    def _get_client(self):

        if genai is None:
            logger.error(
                "Google GenAI SDK missing. "
                "Install google-genai."
            )
            return None

        if self._client is None:

            key = get_api_key()

            if not key:
                logger.error(
                    "GEMINI_API_KEY is missing or empty."
                )
                return None

            try:
                self._client = genai.Client(
                    api_key=key
                )

                logger.info(
                    "Gemini client initialized successfully."
                )

            except Exception:
                logger.exception(
                    "Gemini client initialization failed."
                )
                return None

        return self._client

    # ASK GEMINI
    def _ask_gemini(self, prompt: str):

        client = self._get_client()

        if client is None:
            return None

        try:

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt
            )

            answer = (response.text or "").strip()

            if not answer:

                logger.error(
                    "Gemini returned an empty response."
                )

                return None

            logger.info(
                "Gemini generated response successfully."
            )

            return answer

        except Exception:

            logger.exception(
                "Gemini API request failed. "
                "Check API key, model access and quota."
            )

            return None

    # WEB SEARCH
    def _search_web(self, question: str):

        try:

            results = web_search(question)

            return results or []

        except Exception:

            logger.exception(
                "Web search failed."
            )

            return []

    # MAIN ANSWER FUNCTION
    def answer(
        self,
        question: str,
        db,
        history=None,
        mode: str = "fast"
    ) -> dict:

        question = (question or "").strip()

        if not question:

            return {
                "answer": "Kuch poochho to sahi! 😊",
                "sources": []
            }

        mode = (mode or "fast").lower()

        if mode not in ("fast", "deep"):
            mode = "fast"

        system_prompt = (
            DEEP_PROMPT
            if mode == "deep"
            else FAST_PROMPT
        )

        # 1. AI NAME
        if _is_ai_name_question(question):

            return {
                "answer": (
                    "Main RAMA hoon. 😊 "
                    "Tumhara personal AI assistant!"
                ),
                "sources": []
            }

        # 2. USER NAME
        if _is_user_name_question(question):

            try:

                mem = get_memory(db, "user_name")

                if mem:

                    return {
                        "answer": (
                            f"Tumhara naam {mem.value} hai. 😊"
                        ),
                        "sources": []
                    }

            except Exception:

                logger.exception(
                    "User name memory lookup failed."
                )

            return {
                "answer": (
                    "Mujhe tumhara naam abhi pata nahi. "
                    "Batao: 'mera naam X hai' "
                    "likhkar yaad kara do!"
                ),
                "sources": []
            }

        # 3. PERSONAL MEMORY
        try:

            memories = search_memories(
                db,
                question
            )

        except Exception:

            logger.exception(
                "Memory search failed."
            )

            memories = []

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
                    "Answer found in personal memory."
                )

                return {
                    "answer": _clean_answer(mem.value),
                    "sources": []
                }

        # 4. CURRENT INFORMATION / WEB SEARCH
        sources = []

        if _needs_fresh_info(question):

            sources = self._search_web(question)

            if sources:

                web_text = "\n".join(
                    (
                        f"- {r.get('title', '')}: "
                        f"{r.get('snippet', '')}"
                    )
                    for r in sources[:5]
                )

                gemini_answer = self._ask_gemini(
                    f"{system_prompt}\n\n"
                    f"Search results:\n{web_text}\n\n"
                    f"Question: {question}\n\n"
                    "Answer only using the supplied search results. "
                    "Do not invent missing information. "
                    "If the results are insufficient, say so."
                )

                if gemini_answer:

                    return {
                        "answer": _clean_answer(
                            gemini_answer
                        ),
                        "sources": sources
                    }

                # Gemini unavailable: use search snippet
                first = (
                    sources[0].get("snippet", "").strip()
                )

                if first:

                    return {
                        "answer": _clean_answer(first),
                        "sources": sources
                    }

        # 5. CONVERSATION HISTORY
        history_text = ""

        if history:

            try:

                lines = []

                for item in history[-10:]:

                    role = item.get(
                        "role",
                        "user"
                    )

                    content = item.get(
                        "content",
                        ""
                    )

                    if content:

                        lines.append(
                            f"{role}: {content}"
                        )

                history_text = "\n".join(lines)

            except Exception:

                logger.exception(
                    "Conversation history processing failed."
                )

        # 6. NORMAL GEMINI CONVERSATION
        prompt = system_prompt + "\n\n"

        if history_text:

            prompt += (
                "Previous conversation:\n"
                f"{history_text}\n\n"
            )

        prompt += (
            f"Current user message: {question}\n\n"
            "Respond naturally in the same language "
            "as the user. Understand the conversation "
            "context. Do not introduce yourself unless asked."
        )

        gemini_answer = self._ask_gemini(prompt)

        if gemini_answer:

            return {
                "answer": _clean_answer(
                    gemini_answer
                ),
                "sources": [],
                "mode": mode
            }

        # 7. FALLBACK
        # Search only when the question appears factual.
        if not sources and _needs_fresh_info(question):

            sources = self._search_web(question)

        if sources:

            first = (
                sources[0].get("snippet", "").strip()
            )

            if first:

                return {
                    "answer": _clean_answer(first),
                    "sources": sources
                }

        logger.error(
            "All answer methods failed for this request."
        )

        return {
            "answer": (
                "Abhi RAMA ki AI service respond nahi kar rahi. "
                "Thodi der baad dobara try karo. 😊"
            ),
            "sources": []
        }
