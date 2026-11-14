"""Rama — web search (sirf Python stdlib urllib, koi extra package nahi).

Sources (koi API key nahi chahiye):
1. DuckDuckGo Instant Answer API — https://api.duckduckgo.com/?q=...&format=json
2. Wikipedia REST API — https://en.wikipedia.org/api/rest_v1/page/summary/...

web_search(query) -> list of {title, snippet, url, source}. Error pe [].
"""
import json
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Rama/1.0 (AI chat app)"}

# Common Hindi/Hinglish words -> English (taaki Hindi sawal pe bhi web results milen)
HI_TO_EN = {
    "bharat": "India", "hindustan": "India", "rajdhani": "capital",
    "sabse bada": "largest", "sabse chhota": "smallest",
    "kitne": "how many", "kaun": "who", "kya hai": "what is",
    "mausam": "weather", "khabar": "news", "kimat": "price",
    "paani": "water", "aabadi": "population", "aaj": "today",
    "grah": "planet", "samundra": "ocean", "nadi": "river",
    "pahad": "mountain", "desh": "country", "duniya": "world",
    "sawal": "question", "jawab": "answer", "kitab": "book",
    "bada": "big", "chhota": "small", "purana": "old", "naya": "new",
    "ubalta": "boiling", "ubalti": "boiling", "jamta": "freezing",
}


def _translate_query(query: str) -> str:
    """Hindi/Hinglish sawal ko English search terms me badlo.
    "Bharat ki rajdhani kya hai?" -> "India capital" (DDG/Wikipedia ke liye).
    Word-boundary matching — substring nahi (warna "kaunsa" -> "whosa" ho jata)."""
    out = query.lower()
    # Pehle multi-word phrases (sabse bada, kya hai) replace karo
    for hi, en in HI_TO_EN.items():
        if " " in hi:
            out = out.replace(hi, en)
    # Phir word-by-word map karo (poora word match, substring nahi)
    words = out.replace("?", " ").split()
    mapped = []
    for w in words:
        if w in HI_TO_EN:
            mapped.extend(HI_TO_EN[w].split())
        else:
            mapped.append(w)
    # Filler words hatao (Hindi stopwords + English question words)
    stop = {
        "ki", "ka", "ke", "ko", "se", "me", "ne", "hai", "h", "kya", "kaun",
        "kab", "kahan", "kaise", "kyun", "yeh", "woh", "ye", "wo", "aur",
        "bhi", "toh", "to", "hi", "na", "nahi", "is", "the", "a", "an",
        "of", "in", "on", "what", "who", "when", "where", "how", "why",
        "which", "are", "was", "were", "do", "does",
        "kaunsa", "kaunsi", "kaunse", "konsa", "konsi", "kon",
        "kis", "kisko", "kiske", "kyaa", "kaisa", "kaisi", "par",
    }
    keep = [w for w in mapped if w not in stop]
    return " ".join(keep) or query


def _get_json(url: str, timeout: int = 10):
    """URL se JSON lao; error pe None."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _ddg_search(query: str) -> list[dict]:
    """DuckDuckGo Instant Answer."""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    data = _get_json(url)
    if not data:
        return []
    results = []
    # Seedha jawab (Abstract)
    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        results.append({
            "title": data.get("Heading") or query,
            "snippet": abstract,
            "url": data.get("AbstractURL") or "",
            "source": "duckduckgo.com",
        })
    # Related topics
    for topic in data.get("RelatedTopics") or []:
        if not isinstance(topic, dict):
            continue
        text = (topic.get("Text") or "").strip()
        first_url = (topic.get("FirstURL") or "").strip()
        if text:
            results.append({
                "title": text[:80],
                "snippet": text,
                "url": first_url,
                "source": "duckduckgo.com",
            })
        if len(results) >= 5:
            break
    return results


def _wikipedia_search(query: str) -> list[dict]:
    """Wikipedia summary."""
    title = urllib.parse.quote(query.strip().replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    data = _get_json(url)
    if not data or data.get("type") == "disambiguation":
        return []
    extract = (data.get("extract") or "").strip()
    if not extract:
        return []
    page_url = ""
    content_urls = data.get("content_urls") or {}
    desktop = content_urls.get("desktop") or {}
    page_url = desktop.get("page", "")
    return [{
        "title": data.get("title") or query,
        "snippet": extract,
        "url": page_url,
        "source": "wikipedia.org",
    }]


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Web search — DDG pehle, phir Wikipedia. Error pe khali list.
    Hindi sawal pe pehle original query, phir English-translated query try karo."""
    if not query or not query.strip():
        return []
    query = query.strip()
    results = _search_once(query, max_results)
    if not results:
        translated = _translate_query(query)
        if translated.lower() != query.lower():
            results = _search_once(translated, max_results)
    return results


def _search_once(query: str, max_results: int = 5) -> list[dict]:
    """Ek query se DDG + Wikipedia results lao."""
    results = []
    try:
        results.extend(_ddg_search(query))
    except Exception:
        pass
    if len(results) < max_results:
        try:
            results.extend(_wikipedia_search(query))
        except Exception:
            pass
    # Dedupe (same URL/snippet dobara nahi)
    seen = set()
    out = []
    for r in results:
        key = (r.get("url") or "") + "|" + (r.get("snippet") or "")[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= max_results:
            break
    return out
