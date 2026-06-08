import json, urllib.request
from responder.llm.prompt import ACTIVE_LISTENER_SYSTEM
from responder.llm.chat import _ollama_available, _get_model, OLLAMA_URL
from responder.formatter import result_block


def maybe_hint(conn, new_text: str):
    if not new_text.strip() or len(new_text.strip()) < 10:
        return None
    if not _ollama_available():
        return None
    payload = json.dumps({
        "model": _get_model(), "stream": False,
        "messages": [{"role": "system", "content": ACTIVE_LISTENER_SYSTEM},
                     {"role": "user", "content": new_text}]
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        reply = data["message"]["content"].strip()
        if reply.startswith("[no hint]") or not reply:
            return None
        return result_block("Jeles — note", reply)
    except Exception:
        return None
