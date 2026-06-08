"""
Layered LLM for UTETY TUI.
Ollama (local) → Willow free fleet → Willow paid tier.
Falls through on timeout or error at each tier.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_TIMEOUT = int(os.environ.get("UTETY_OLLAMA_TIMEOUT_SECS", "55"))

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = os.environ.get("UTETY_GROQ_MODEL", "llama-3.1-8b-instant")

# Gerald barely speaks — smallest model is fine.
PROFESSOR_MODELS: dict[str, str] = {
    "Gerald": os.environ.get("UTETY_GERALD_MODEL", "llama3.2:1b"),
}
DEFAULT_MODEL = os.environ.get("UTETY_OLLAMA_MODEL", "llama3.1:8b")


def ask(prompt: str, professor: str = "", on_chunk=None) -> dict:
    """Try Ollama → Groq. Returns {ok, text, provider, tier}.

    on_chunk: optional callable(token: str) called with each streamed token.
              When provided, Ollama is used in streaming mode.
    """
    model = PROFESSOR_MODELS.get(professor, DEFAULT_MODEL)

    result = _ask_ollama(prompt, model, on_chunk=on_chunk)
    if result["ok"]:
        return result

    return _ask_groq(prompt)


def _ask_ollama(prompt: str, model: str = DEFAULT_MODEL, on_chunk=None) -> dict:
    try:
        streaming = on_chunk is not None
        payload = json.dumps({"model": model, "prompt": prompt, "stream": streaming}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            if streaming:
                full_text = ""
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    try:
                        chunk_data = json.loads(line.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    token = chunk_data.get("response", "")
                    if token:
                        full_text += token
                        on_chunk(token)
                    if chunk_data.get("done"):
                        break
                text = full_text.strip()
            else:
                body = json.loads(resp.read())
                text = body.get("response", "").strip()
            if not text:
                return {"ok": False, "error": "empty response", "tier": "ollama"}
            return {"ok": True, "text": text, "provider": model, "tier": "ollama"}
    except urllib.error.URLError:
        return {"ok": False, "error": "ollama unreachable", "tier": "ollama"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tier": "ollama"}


_BINDER_CATEGORIES = [
    "academic inquiry",
    "student grievance",
    "bureaucratic appeal",
    "administrative matter",
    "correspondence from faculty",
    "general correspondence",
]


def categorize_for_binder(user_message: str) -> str:
    """Quick LLM call to categorize a message for Binder's filing system. Fast path only."""
    cats = ", ".join(f'"{c}"' for c in _BINDER_CATEGORIES)
    prompt = (
        f"Categories: {cats}\n"
        "Classify this student message into exactly one category above. "
        "Reply with only the category name.\n"
        f"Message: {user_message[:300]}\nCategory:"
    )
    result = _ask_ollama(prompt, model="llama3.2:3b")
    if not result["ok"]:
        return "general correspondence"
    text = result["text"].strip().lower().strip('"').strip("'").rstrip(".")
    for cat in _BINDER_CATEGORIES:
        if cat in text or text in cat:
            return cat
    return "general correspondence"


def _ask_groq(prompt: str, model: str = GROQ_DEFAULT_MODEL) -> dict:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return {"ok": False, "error": "GROQ_API_KEY not set", "tier": "groq"}
    try:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1024,
        }).encode()
        req = urllib.request.Request(
            GROQ_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            text = body["choices"][0]["message"]["content"].strip()
            if not text:
                return {"ok": False, "error": "empty response", "tier": "groq"}
            return {"ok": True, "text": text, "provider": model, "tier": "groq"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc), "tier": "groq"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tier": "groq"}
