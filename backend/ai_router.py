
"""RAMA AI Router V3
Intelligent conversation, identity, memory, web search and Gemini.
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



MODEL = "gemini-3.8-flash"



SYSTEM_PROMPT = """
You are RAMA, an intelligent and helpful personal AI assistant.

IDENTITY:
- Your name is RAMA.
- You are the user's AI assistant.
- Never claim to be another AI.

BEHAVIOUR:
- Understand Hindi, Hinglish and English.
- Reply in the same language as the user.
- Be friendly, natural and conversational.
- Remember the available conversation history.
- Give accurate and useful answers.
- Never invent facts, URLs, sources or statistics.
- If you do not know something, say so honestly.
- Do not unnecessarily introduce yourself in every reply.
- Do not unnecessarily mention web searches.

IMPORTANT:
- Ordinary greetings should receive short greetings.
- Identity questions should receive your identity.
- Never confuse the user's identity with your own.
"""


FAST_PROMPT = SYSTEM_PROMPT + """
MODE: FAST

Give direct, concise and useful answers.
Avoid unnecessary explanations.
"""


DEEP_PROMPT = SYSTEM_PROMPT + """
MODE: DEEP

Give detailed and well-organized explanations.
Explain important steps, concepts and conclusions.
Include examples where useful.
Do not reveal private internal reasoning.
"""


# --------------------------------------------------
# TEXT CLEANING
# --------------------------------------------------

def _clean_answer(text):
    if not text:
        return ""

    text = str(text)

    text = re.sub(r"&#\w+;", "", text)

    replacements = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&nbsp;": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _normalize(text):
    return re.sub(
        r"\s+",
        " ",
        (text or "").lower().strip()
    )


# --------------------------------------------------
# GREETING DETECTION
# --------------------------------------------------

def _is_greeting(question):
    q = _normalize(question)

    # Standalone greetings
    greetings = {
        "hello",
        "hello!",
        "hi",
        "hi!",
        "hey",
        "hey!",
        "hii",
        "hiii",
        "namaste",
        "namaskar",
        "pranam",
        "good morning",
        "good afternoon",
        "good evening",
    }

    if q in greetings:
        return True

    # Greeting followed by the assistant's name
    if re.fullmatch(
        r"(hello|hi|hey|hii|hiii)\s+(rama|ram)?[!. ]*",
        q
    ):
        return True

    return False


def _is_how_are_you(question):
    q = _normalize(question)

    patterns = [
        r"^how are you[?!. ]*$",
        r"^how are you doing[?!. ]*$",
        r"^kaise ho[?!. ]*$",
        r"^kaisa hai[?!. ]*$",
        r"^kaisi ho[?!. ]*$",
        r"^kya haal hai[?!. ]*$",
        r"^sab badhiya[?!. ]*$",
    ]

    return any(re.search(p, q) for p in patterns)


# --------------------------------------------------
# IDENTITY DETECTION
# --------------------------------------------------

def _is_ai_name_question(question):
    q = _normalize(question)

    patterns = [
        r"\bwho are you\b",
        r"\bwho r u\b",
        r"\bwhat is your name\b",
        r"\bwhat's your name\b",
        r"\bwhats your name\b",
        r"\btum kaun ho\b",
        r"\btum kon ho\b",
        r"\baap kaun ho\b",
        r"\baap kon ho\b",
        r"\btumhara naam kya\b",
        r"\baapka naam kya\b",
        r"\btera naam kya\b",
        r"\bwho made you\b",
        r"\bwho created you\b",
    ]

    return any(re.search(p, q) for p in patterns)


def _is_user_name_question(question):
    q = _normalize(question)

    patterns = [
        r"\bmera naam kya\b",
        r"\bwhat is my name\b",
        r"\bwhat's my name\b",
        r"\bwhats my name\b",
        r"\bdo you know my name\b",
    ]

    return any(re.search(p, q) for p in patterns)


# --------------------------------------------------
# WEB SEARCH INTENT
# --------------------------------------------------

def _needs_fresh_info(question):
    q = _normalize(question)

    patterns = [
        r"\blatest news\b",
        r"\btoday's news\b",
        r"\btodays news\b",
        r"\bbreaking news\b",
        r"\blatest updates\b",
        r"\bcurrent news\b",
        r"\bweather today\b",
        r"\bweather now\b",
        r"\bcurrent weather\b",
        r"\blive score\b",
        r"\bcurrent score\b",
        r"\btoday's price\b",
        r"\btodays price\b",
        r"\bcurrent price\b",
        r"\bprice right now\b",
        r"\bcurrent president\b",
        r"\bcurrent prime minister\b",
        r"\bwho won\b.*\b(today|yesterday|recently)\b",
        r"\bwhat happened today\b",
        r"\bwhat happened yesterday\b",
        r"\baaj ki khabar\b",
        r"\baaj ki news\b",
        r"\btaaza khabar\b",
        r"\blatest khabar\b",
        r"\babhi ka mausam\b",
        r"\baaj ka mausam\b",
        r"\baaj ka score\b",
        r"\baaj ka result\b",
        r"\babhi ka price\b",
        r"\baaj ka price\b",
        r"\blatest ai news\b",
    ]

    if any(re.search(p, q) for p in patterns):
        return True

    # Explicit current-information keywords
    fresh_words = {
        "latest",
        "breaking",
        "today",
        "currently",
        "recently",
        "live",
        "forecast",
        "weather",
        "mausam",
        "khabar",
        "samachar",
        "taaza",
        "abhi",
    }

    words = set(re.findall(r"[a-zA-Z\u0900-\u097F]+", q))

    return bool(words & fresh_words)


# --------------------------------------------------
# SOURCE FILTERING
# --------------------------------------------------

def _dedupe_sources(sources):
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

        # Keep one result per domain to avoid repeated links
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


# --------------------------------------------------
# MAIN AI ROUTER
# --------------------------------------------------

class AIRouter:

    def __init__(self):
        self._client = None

    # Gemini client
    def _get_client(self):

        if genai is None:
            return None

        if self._client is None:

            try:
                key = get_api_key()

                if not key:
                    return None

                self._client = genai.Client(
                    api_key=key
                )

            except Exception:
                return None

        return self._client

    # Ask Gemini
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
                answer = _clean_answer(answer)

                if answer:
                    return answer

        except Exception as error:
            print("RAMA Gemini Error:", str(error))

        return None

    # Search internet
    def _search(self, question):

        try:
            results = web_search(question)

            return _dedupe_sources(results)

        except Exception as error:
            print("RAMA Search Error:", str(error))
            return []

    # Main answer function
    def answer(
        self,
        question,
        db,
        history=None,
        mode="fast"
    ):

        question = (question or "").strip()

        if not question:
            return {
                "answer": "Kuch poochho to sahi! 😊",
                "sources": [],
            }

        mode = (mode or "fast").lower()

        if mode not in ("fast", "deep"):
            mode = "fast"

        system_prompt = (
            DEEP_PROMPT
            if mode == "deep"
            else FAST_PROMPT
        )

        # ------------------------------------------
        # 1. AI IDENTITY
        # ------------------------------------------

        if _is_ai_name_question(question):

            return {
                "answer": (
                    "Main RAMA hoon! 😊 "
                    "Tumhara personal AI assistant."
                ),
                "sources": [],
            }

        # ------------------------------------------
        # 2. USER NAME
        # ------------------------------------------

        if _is_user_name_question(question):

            try:
                mem = get_memory(db, "user_name")

                if mem:
                    return {
                        "answer": (
                            f"Tumhara naam {mem.value} hai. 😊"
                        ),
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

        # ------------------------------------------
        # 3. GREETING
        # ------------------------------------------

        if _is_greeting(question):

            q = _normalize(question)

            if "good morning" in q:
                answer = "Good morning! ☀️ Kaise ho?"

            elif "good afternoon" in q:
                answer = "Good afternoon! 😊 Kaise ho?"

            elif "good evening" in q:
                answer = "Good evening! 😊 Kaise ho?"

            else:
                # IMPORTANT:
                # Normal hello par self-introduction nahi.
                answer = "Hello! 👋 Kaise ho? Batao, kya chal raha hai?"

            return {
                "answer": answer,
                "sources": [],
            }

        # ------------------------------------------
        # 4. HOW ARE YOU
        # ------------------------------------------

        if _is_how_are_you(question):

            return {
                "answer": (
                    "Main badhiya hoon! 😊 "
                    "Tum batao, kaise ho?"
                ),
                "sources": [],
            }

        # ------------------------------------------
        # 5. PERSONAL MEMORY
        # ------------------------------------------

        try:
            memories = search_memories(db, question)
        except Exception:
            memories = []

        q_words = set(content_words(question))

        for mem in memories:

            try:
                saved_words = set(
                    content_words(
                        f"{mem.key} {mem.value}"
                    )
                )

                overlap = q_words & saved_words

                if len(overlap) >= 2:

                    return {
                        "answer": _clean_answer(mem.value),
                        "sources": [],
                    }

            except Exception:
                continue

        # ------------------------------------------
        # 6. CURRENT INFORMATION SEARCH
        # ------------------------------------------

        sources = []

        if _needs_fresh_info(question):

            sources = self._search(question)

            if sources:

                web_text = "\n".join(
                    (
                        f"- {item.get('title', '')}: "
                        f"{item.get('snippet', '')}"
                    )
                    for item in sources[:5]
                )

                prompt = (
                    system_prompt
                    + "\n\nSearch results:\n"
                    + web_text
                    + "\n\nQuestion: "
                    + question
                    + "\n\nAnswer using only the supplied "
                    "search results for current facts. "
                    "Do not invent missing information. "
                    "Respond in the user's language."
                )

                answer = self._ask_gemini(prompt)

                if answer:

                    return {
                        "answer": answer,
                        "sources": sources,
                    }

                snippets = [
                    item.get("snippet", "").strip()
                    for item in sources
                    if item.get("snippet", "").strip()
                ]

                if snippets:

                    return {
                        "answer": _clean_answer(snippets[0]),
                        "sources": sources,
                    }

        # ------------------------------------------
        # 7. CONVERSATION HISTORY
        # ------------------------------------------

        history_text = ""

        if history:

            try:
                lines = []

                for item in history[-8:]:

                    role = item.get("role", "user")
                    content = item.get("content", "")

                    if role not in ("user", "assistant"):
                        continue

                    lines.append(
                        f"{role}: {content}"
                    )

                history_text = "\n".join(lines)

            except Exception:
                history_text = ""

        # ------------------------------------------
        # 8. NORMAL GEMINI CHAT
        # ------------------------------------------

        prompt = system_prompt + "\n\n"

        if history_text:

            prompt += (
                "Conversation history:\n"
                + history_text
                + "\n\n"
            )

        prompt += (
            "Current user message:\n"
            + question
            + "\n\n"
            "Answer naturally and directly. "
            "Use the conversation history when relevant. "
            "Do not search the internet for normal conversation. "
            "Reply in the same language as the user."
        )

        answer = self._ask_gemini(prompt)

        if answer:

            return {
                "answer": answer,
                "sources": [],
            }

        # ------------------------------------------
        # 9. HONEST FALLBACK
        # ------------------------------------------

        # Never search normal messages just because Gemini failed.

        return {
            "answer": (
                "Abhi mera AI service respond nahi kar raha. "
                "Thodi der baad dobara try karo. 😊"
            ),
            "sources": [],
        }
