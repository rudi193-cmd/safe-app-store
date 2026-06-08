"""
llm_client.py — Local-first LLM adapter (Ollama default).

b17: LGLLM1  ΔΣ=42
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

DEFAULT_OLLAMA_BASE = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_TIMEOUT = 120


def llm_config() -> dict[str, str]:
    """Resolved provider settings from environment."""
    return {
        "provider": os.environ.get("LAW_GAZELLE_LLM_PROVIDER", "ollama").lower(),
        "base_url": os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE).rstrip("/"),
        "model": os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
    }


def generate(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    Generate text from the configured local model.

    Returns: {ok, text, model, provider, error}
    """
    cfg = llm_config()
    provider = cfg["provider"]
    if provider != "ollama":
        return {
            "ok": False,
            "text": "",
            "model": model or cfg["model"],
            "provider": provider,
            "error": f"Unsupported provider: {provider}. Only ollama is implemented.",
        }

    url = f"{(base_url or cfg['base_url'])}/api/generate"
    payload: dict[str, Any] = {
        "model": model or cfg["model"],
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = (data.get("response") or "").strip()
        return {
            "ok": True,
            "text": text,
            "model": data.get("model") or payload["model"],
            "provider": "ollama",
            "error": None,
        }
    except requests.Timeout:
        return {
            "ok": False,
            "text": "",
            "model": payload["model"],
            "provider": "ollama",
            "error": f"Ollama request timed out after {timeout}s",
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "text": "",
            "model": payload["model"],
            "provider": "ollama",
            "error": str(exc),
        }
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "text": "",
            "model": payload["model"],
            "provider": "ollama",
            "error": f"Invalid JSON from Ollama: {exc}",
        }


def health_check(*, base_url: str | None = None, timeout: int = 5) -> dict[str, Any]:
    """Ping Ollama tags endpoint."""
    cfg = llm_config()
    url = f"{(base_url or cfg['base_url'])}/api/tags"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        models = [m.get("name") for m in resp.json().get("models", [])]
        return {"ok": True, "models": models, "error": None}
    except requests.RequestException as exc:
        return {"ok": False, "models": [], "error": str(exc)}
