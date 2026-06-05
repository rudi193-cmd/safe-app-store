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

# Gerald barely speaks — smallest model is fine.
PROFESSOR_MODELS: dict[str, str] = {
    "Gerald": os.environ.get("UTETY_GERALD_MODEL", "llama3.2:1b"),
}
DEFAULT_MODEL = os.environ.get("UTETY_OLLAMA_MODEL", "llama3.1:8b")


def ask(prompt: str, professor: str = "") -> dict:
    """Try Ollama → Willow free → Willow paid. Returns {ok, text, provider, tier}."""
    model = PROFESSOR_MODELS.get(professor, DEFAULT_MODEL)

    result = _ask_ollama(prompt, model)
    if result["ok"]:
        return result

    result = _ask_willow(prompt, tier="free")
    if result["ok"]:
        return result

    return _ask_willow(prompt, tier="paid")


def _ask_ollama(prompt: str, model: str = DEFAULT_MODEL) -> dict:
    try:
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
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


def _ask_willow(prompt: str, tier: str = "free") -> dict:
    try:
        import safe_integration as _willow

        result = _willow.ask_raw(prompt, tier=tier)
        if result and result.get("ok"):
            return {
                "ok": True,
                "text": result.get("result", "").strip(),
                "provider": result.get("provider", tier),
                "tier": tier,
            }
        return {"ok": False, "error": (result or {}).get("error", "willow failed"), "tier": tier}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tier": tier}
