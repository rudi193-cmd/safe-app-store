import json, urllib.request, urllib.error
from pathlib import Path
from responder.formatter import result_block
from responder.llm.prompt import JELES_SYSTEM
import db.persons as persons_db

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b"


def _ollama_available() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _get_model() -> str:
    p = Path.home() / ".squirrel" / "config.json"
    if p.exists():
        try:
            return json.loads(p.read_text()).get("ollama_model", DEFAULT_MODEL)
        except Exception:
            pass
    return DEFAULT_MODEL


def _build_context(conn, text: str) -> str:
    candidates = [w for w in text.split() if w and w[0].isupper() and len(w) > 2][:4]
    found = []
    for c in candidates:
        found.extend(persons_db.search_persons(conn, c)[:2])
    if not found:
        return ""
    lines = ["Known persons in the tree:"]
    for p in found[:6]:
        line = f"- {p['full_name']} (id={p['id']})"
        if p.get("birth_date"):  line += f", b.{p['birth_date']}"
        if p.get("birth_place"): line += f", {p['birth_place']}"
        lines.append(line)
    return "\n".join(lines)


def respond(conn, user_text: str) -> str:
    if not _ollama_available():
        return result_block("Jeles (offline)",
            "_Ollama is not running. Start with `ollama serve` to enable Chat mode._")
    context = _build_context(conn, user_text)
    system = JELES_SYSTEM + (f"\n\nSession context:\n{context}" if context else "")
    payload = json.dumps({
        "model": _get_model(), "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_text}]
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return result_block("Jeles", data["message"]["content"].strip())
    except Exception as e:
        return result_block("Jeles (error)", f"_LLM call failed: {e}_")
