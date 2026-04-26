"""
local_oral_chat.py -- Local proxy for the NASA oral-chat edge function.
Mirrors the Supabase edge function API exactly.

Startup:
  1. Registers 'nasa-oral-chat' with Willow's agent_registry
  2. Gets auto-assigned port from the 84xx range
  3. Writes PUBLIC_ORAL_CHAT_URL to site/.env.local
  4. Starts serving

Run: python local_oral_chat.py
Then: cd site && npm run dev
"""
import json
import sys
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Willow core
_WILLOW_ROOT = Path(__file__).parent.parent / "Willow"
WILLOW_CORE = str(_WILLOW_ROOT / "core")
sys.path.insert(0, str(_WILLOW_ROOT))  # for "from core.db import ..."
sys.path.insert(0, WILLOW_CORE)         # for "import llm_router"

import llm_router
import agent_registry

llm_router.load_keys_from_json()

# Riggs persona -- imported from personas.py (single source of truth)
_REPO = Path(__file__).parent
sys.path.insert(0, str(_REPO))
from personas import get_persona

USERNAME = "Sweet-Pea-Rudi19"
AGENT_NAME = "riggs-archive"
SITE_ENV_LOCAL = _REPO / "site" / ".env.local"

SYSTEM_PROMPT = get_persona("NASA_Riggs")


def _register_and_get_port() -> int:
    """Register with Willow agent_registry and get auto-assigned port."""
    agent_registry.register_agent(
        username=USERNAME,
        name=AGENT_NAME,
        display_name="Riggs — NASA Archive",
        trust_level="WORKER",
        agent_type="persona",
        purpose="Prof. Riggs, Applied Reality Engineering. Voice of the North America Scootering Archive.",
    )
    port = agent_registry.assign_port(USERNAME, AGENT_NAME, server_type="oral-chat")
    return port


def _write_env_local(port: int):
    """Write PUBLIC_ORAL_CHAT_URL to site/.env.local so Astro picks it up."""
    SITE_ENV_LOCAL.write_text(
        f"# Auto-written by local_oral_chat.py on startup\n"
        f"PUBLIC_ORAL_CHAT_URL=http://localhost:{port}\n",
        encoding="utf-8",
    )


def _call_fleet(prompt: str) -> str:
    r = llm_router.ask(prompt, preferred_tier="free")
    if r and r.content:
        return r.content.strip()
    raise RuntimeError("All fleet providers failed")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"oral-chat: {fmt % args}", flush=True)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/functions/v1/oral-chat":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        message = body.get("message", "").strip()
        slug = body.get("slug", "").strip()
        page_type = body.get("page_type", "general").strip()
        history = body.get("history", [])

        if not message:
            self._json(400, {"error": "message required"})
            return

        # Build context based on page type
        context = ""
        if page_type == "rally" and slug:
            context = f'\nThe user is sharing memories about the rally: "{slug.replace("-", " ")}"'
        elif page_type == "photo":
            context = "\nThe user is looking at a rally photo and wants to talk about it."
        elif page_type == "club":
            context = "\nThe user is browsing scooter clubs and might want to know about club history."
        elif page_type == "patch":
            context = "\nThe user is looking at rally patches and might have a patch story to share."

        system_content = SYSTEM_PROMPT + context
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Riggs'}: {m['content']}"
            for m in history[-10:]
        )
        prompt = f"{system_content}\n\n{history_text}\nUser: {message}\nRiggs:"

        try:
            reply = _call_fleet(prompt)
            self._json(200, {"reply": reply})
        except Exception as e:
            print(f"Fleet error: {type(e).__name__}: {e}", flush=True)
            self._json(503, {"error": "LLM unavailable"})

    def _json(self, status: int, data: dict):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = _register_and_get_port()
    _write_env_local(port)

    url = f"http://localhost:{port}/functions/v1/oral-chat"
    print(f"NASA oral-chat proxy: {url}", flush=True)
    print(f"site/.env.local updated with PUBLIC_ORAL_CHAT_URL", flush=True)
    print(f"Now run: cd site && npm run dev", flush=True)

    HTTPServer(("localhost", port), Handler).serve_forever()
