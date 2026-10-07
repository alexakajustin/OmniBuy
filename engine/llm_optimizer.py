"""LLM Query Optimizer using Gemini (primary) and DeepSeek (fallback).

The LLM is only allowed to *shorten* the user's query (e.g. keep the part
number and drop filler words). It is never trusted blindly: every suggestion
is validated against the original query, and anything containing words that
were not typed by the user is rejected as a hallucination. When in doubt, the
original query is used.
"""

import os
import re
import json
import logging
import threading
import unicodedata
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# Tried in order; the next one is used when a model is out of quota (429), retired (404) or down.
# Flash Lite models have far higher free-tier quotas than Flash and are plenty for this task.
GEMINI_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")
    if m.strip()
]
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

LLM_TIMEOUT = 10  # seconds per provider — the search waits on this
MAX_TERM_LENGTH = 80

SYSTEM_PROMPT = (
    "You turn a shopper's search text into the best term to type into an IT / networking "
    "supplier's search bar.\n"
    "Rules:\n"
    "1. Use ONLY words and codes that appear in the user's text. Never add, guess, complete, "
    "translate or 'correct' anything. Never invent a part number.\n"
    "2. If the text contains a manufacturer part number / SKU / exact model code, return just "
    "that code, exactly as written.\n"
    "3. Otherwise return the 1-4 most distinctive words from the text (brand, product type, "
    "key spec), dropping filler words.\n"
    "4. If the text is already short and specific, return it unchanged.\n"
    'Respond with JSON only: {"search_term": "<term>"}'
)


@dataclass(frozen=True)
class OptimizedQuery:
    """Outcome of the AI optimization step."""

    original: str
    term: str          # what will actually be searched
    source: str        # "gemini" | "deepseek" | "original"
    note: str = ""     # human-readable explanation (e.g. why a suggestion was rejected)

    @property
    def changed(self) -> bool:
        return self.term != self.original


# Cache only successful LLM answers, so a transient API outage is not remembered.
_cache: dict[str, OptimizedQuery] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 256


def optimize_search_query(user_query: str) -> OptimizedQuery:
    """Ask an LLM for a shorter search term and validate it against the original.

    Never raises. Falls back to the original query when the providers are not
    configured, fail, or return something that is not grounded in the query.
    """
    query = user_query.strip()
    if not query:
        return OptimizedQuery(query, query, "original", "Query gol.")

    with _cache_lock:
        cached = _cache.get(query)
    if cached:
        return cached

    rejections = []
    failures = []
    providers = (("gemini", _call_gemini), ("deepseek", _call_deepseek))
    for name, call in providers:
        try:
            raw = call(query)
        except ProviderError as e:
            logger.error("[AI/%s] %s", name, e)
            failures.append(f"{name}: {e}")
            continue
        if raw is None:
            continue

        term = _clean_term(raw)
        problem = _validate_term(term, query)
        if problem:
            logger.warning("[AI/%s] Rejected suggestion %r for %r: %s", name, raw, query, problem)
            rejections.append(f"{name}: {problem}")
            continue

        result = OptimizedQuery(query, term, name)
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
            _cache[query] = result
        return result

    if rejections:
        note = "Sugestia AI a fost respinsă (" + "; ".join(rejections) + ")."
    elif failures:
        note = "AI indisponibil (" + "; ".join(failures) + ")."
    else:
        note = "Nicio cheie API configurată (GEMINI_API_KEY / DEEPSEEK_API_KEY)."
    note += " Folosesc căutarea originală."
    logger.warning("[AI] %s", note)
    return OptimizedQuery(query, query, "original", note)


# --- Validation -------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and strip diacritics ('ș' -> 's') so comparisons are robust."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalize(text))


def _clean_term(raw: str) -> str:
    """Strip quotes/markdown and keep the first line of the model's answer."""
    text = raw.strip().strip("`").strip()
    # The model may wrap the JSON in a code fence or answer in plain text.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and isinstance(data.get("search_term"), str):
                text = data["search_term"]
        except json.JSONDecodeError:
            pass
    text = text.splitlines()[0] if text else ""
    return text.strip().strip("\"'`«»„”“").strip()


def _validate_term(term: str, query: str) -> str | None:
    """Return a reason string if `term` is not safe to search, else None."""
    if not term:
        return "răspuns gol"
    if len(term) > MAX_TERM_LENGTH:
        return "răspuns prea lung"

    term_tokens = _tokens(term)
    if not term_tokens:
        return "răspuns fără litere/cifre"

    query_tokens = set(_tokens(query))
    # Allows "DS7108" to match "DS-7108" in the query (separators dropped).
    query_compact = "".join(_tokens(query))

    invented = [
        t for t in term_tokens
        if t not in query_tokens and not (len(t) >= 4 and t in query_compact)
    ]
    if invented:
        return "conține termeni care nu apar în căutare: " + ", ".join(invented)
    return None


# --- Providers --------------------------------------------------------------
# Each provider returns the raw answer text, None when it is not configured,
# or raises ProviderError with a short, key-free reason.

class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _post(url: str, payload: dict, headers: dict) -> dict:
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
    except requests.Timeout:
        raise ProviderError(f"timeout după {LLM_TIMEOUT}s") from None
    except requests.RequestException as e:
        raise ProviderError(f"eroare de rețea ({type(e).__name__})") from None

    if not response.ok:
        try:
            message = response.json()["error"]["message"]
        except Exception:
            message = response.reason
        raise ProviderError(f"HTTP {response.status_code} {str(message)[:120]}", response.status_code)
    try:
        return response.json()
    except ValueError:
        raise ProviderError("răspuns invalid (nu e JSON)") from None

def _call_gemini(user_query: str) -> str | None:
    if not GEMINI_API_KEY:
        return None

    # Key goes in a header, not the URL, so it never ends up in logged exceptions.
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_query}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {"search_term": {"type": "STRING"}},
                "required": ["search_term"],
            },
        },
    }

    errors = []
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            data = _post(url, payload, headers)
        except ProviderError as e:
            errors.append(f"{model}: {e}")
            # A bad key or bad request fails the same way on every model — don't burn time on the rest.
            if e.status in (400, 401, 403):
                break
            logger.warning("[AI/gemini] %s failed (%s), trying next model", model, e)
            continue
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            errors.append(f"{model}: răspuns fără conținut")
            continue
        return "".join(p.get("text", "") for p in parts).strip() or None

    raise ProviderError("; ".join(errors) or "niciun model configurat")


def _call_deepseek(user_query: str) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        "temperature": 0,
        "max_tokens": 100,
        "response_format": {"type": "json_object"},
    }

    data = _post(url, payload, headers)
    try:
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except (KeyError, IndexError, TypeError):
        raise ProviderError("răspuns fără conținut") from None
