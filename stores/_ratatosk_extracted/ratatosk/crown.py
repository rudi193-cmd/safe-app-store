"""
crown.py — Ratatosk entry point.
b17: L3178  ΔΣ=42

Sovereign Claude Code replacement.
  - Anthropic API direct (no Claude Code wrapper)
  - JSONL session writes (session_reader.py compatible)
  - Hook execution at lifecycle points
  - MCP stdio client (--mcp flag)
  - Grove event posting (RATATOSK_GROVE_CHANNEL)

Usage:
    python -m ratatosk.crown [--trust] [--mcp] [--model MODEL] [--persona NAME]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ratatosk import session as _session
from ratatosk import tools as _tools
from ratatosk import grove as _grove

# ─── Paths ────────────────────────────────────────────────────────────────────

_HOME = Path.home()
_WILLOW_ROOT = Path(os.environ.get("WILLOW_ROOT", str(_HOME / "willow-2.0")))

_PERSONA_SEARCH = [
    _WILLOW_ROOT / "willow" / "fylgja" / "personas",
    _HOME / "agents" / "hanuman" / "personas",
]

_CLAUDE_MD_PATHS = [
    _WILLOW_ROOT / "CLAUDE.md",
    _HOME / "CLAUDE.md",
]

_HOOKS_DIR = _HOME / ".claude" / "hooks"

# ─── Context compaction ───────────────────────────────────────────────────────

_MAX_TURNS = 20
_MAX_CHARS = 200_000


def _compact(history: list[dict]) -> tuple[list[dict], bool]:
    total = sum(
        len(m["content"]) if isinstance(m["content"], str)
        else sum(len(str(b)) for b in m["content"])
        for m in history
    )
    if total <= _MAX_CHARS and len(history) <= _MAX_TURNS * 2:
        return history, False
    keep = history[-(_MAX_TURNS * 2):]
    dropped = len(history) - len(keep)
    notice = {
        "role": "user",
        "content": (
            f"[System note: {dropped} earlier messages compacted. "
            f"Continuing from turn {len(history) // 2 - _MAX_TURNS + 1}.]"
        ),
    }
    return [notice] + keep, True


# ─── System prompt ────────────────────────────────────────────────────────────

def _load_persona(name: str) -> str | None:
    for base in _PERSONA_SEARCH:
        p = base / f"{name}.md"
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text
    return None


def _load_system_prompt(persona: str | None) -> str:
    if persona:
        text = _load_persona(persona)
        if text:
            return text
        print(f"[persona] '{persona}' not found — using default", flush=True)
    parts = []
    for p in _CLAUDE_MD_PATHS:
        if p.exists():
            content = p.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"# {p}\n\n{content}")
    return "\n\n---\n\n".join(parts) if parts else "You are Ratatosk. ΔΣ=42"


# ─── Boot context ─────────────────────────────────────────────────────────────

def _load_boot_context(agent: str) -> str:
    """Read latest handoff from disk. Returns compact 3-line banner or ''."""
    handoff_dir = Path.home() / ".willow" / "handoffs" / agent
    if not handoff_dir.exists():
        return ""
    files = sorted(handoff_dir.glob("session_handoff-*.md"), reverse=True)
    if not files:
        return ""
    try:
        text = files[0].read_text(encoding="utf-8")
        next_bite = ""
        for line in text.splitlines():
            if line.startswith("Q17:"):
                next_bite = line[4:].strip()
                break
        threads = text.count("**[OPEN]")
        lines = [f"  [handoff] {files[0].name}"]
        if threads:
            lines.append(f"  open: {threads} threads")
        if next_bite:
            lines.append(f"  next: {next_bite}")
        return "\n".join(lines)
    except Exception:
        return ""


# ─── Persona gate ─────────────────────────────────────────────────────────────

def _persona_gate(preselect: str | None = None) -> str:
    """
    Show picker, block until user confirms or selects.
    Returns persona context string to prepend to the system prompt.
    Hard stop — every session must cross this gate.
    """
    willow_root = str(_WILLOW_ROOT)
    if willow_root not in sys.path:
        sys.path.insert(0, willow_root)
    try:
        from willow.fylgja import persona as _p
    except ImportError as e:
        print(f"  [persona] unavailable ({e}) — skipping gate", flush=True)
        return ""

    if preselect:
        _p.set_active_persona(preselect)

    print()
    print(_p.render_picker(_p.active_persona()))
    print()
    try:
        raw = input("  ▷ confirm or pick: ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""

    if raw:
        choice = _p.parse_selection(raw)
        if choice and choice != "__create__":
            _p.set_active_persona(choice)

    active = _p.active_persona()
    if active and active != "none":
        ctx = _p.load_persona(active)
        if ctx:
            print(f"  [persona:{active}] loaded", flush=True)
            return ctx
    return ""


# ─── Hooks ────────────────────────────────────────────────────────────────────

def _run_hook(script: str | Path, stdin_data: dict | None = None) -> None:
    if not Path(script).exists():
        return
    try:
        inp = json.dumps(stdin_data).encode() if stdin_data else None
        subprocess.run(
            [sys.executable, str(script)],
            input=inp,
            env=os.environ.copy(),
            timeout=10,
            capture_output=True,
        )
    except Exception:
        pass


def _fire_session_start(session_id: str) -> None:
    _run_hook(_HOOKS_DIR / "session_start.py", {"session_id": session_id})


def _fire_prompt_submit(session_id: str, prompt: str) -> None:
    data = {"session_id": session_id, "prompt": prompt}
    _run_hook(_HOOKS_DIR / "prompt_submit.py", data)


def _fire_stop(session_id: str) -> None:
    _run_hook(_HOOKS_DIR / "stop.py", {"session_id": session_id})


# ─── API credentials ──────────────────────────────────────────────────────────

def _load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    _wr = Path(os.environ.get("WILLOW_ROOT", str(_HOME / "github" / "willow-1.9"))).expanduser()
    for candidate in [
        _HOME / ".ratatosk" / "credentials.json",
        _wr / "credentials.json",
        _HOME / "github" / "willow-1.5" / "credentials.json",  # legacy layout
    ]:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
                key = data.get("ANTHROPIC_API_KEY", "")
                if key:
                    os.environ["ANTHROPIC_API_KEY"] = key
                    return key
            except Exception:
                pass
    return ""


# ─── Main REPL ────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ratatosk — sovereign Claude Code replacement")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--trust", action="store_true",
                        help="Execute tools without per-call confirmation")
    parser.add_argument("--persona", default=None)
    parser.add_argument("--mcp", action="store_true",
                        help="Connect to sap_mcp.py via stdio")
    parser.add_argument("--local", action="store_true",
                        help="Route to local Ollama (llama3.2:1b)")
    args = parser.parse_args()

    use_local = args.local
    model = "llama3.2:1b" if use_local else args.model

    mcp_names: set[str] = set()
    mcp_extra_tools: list[dict] = []
    mcp_call = None

    if not use_local:
        api_key = _load_api_key()
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not found.")
            sys.exit(1)
        try:
            import anthropic
        except ImportError:
            print("ERROR: pip install anthropic")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = None

    if args.mcp:
        print("  [mcp] connecting…", flush=True)
        try:
            from ratatosk import mcp_client
            mcp_extra_tools, mcp_names = mcp_client.start()
            mcp_call = mcp_client.call
            print(f"  [mcp] {len(mcp_names)} tools loaded", flush=True)
        except Exception as e:
            print(f"  [mcp] FAILED: {e} — continuing without MCP tools", flush=True)

    all_tools = _tools.BASE_TOOLS + mcp_extra_tools
    persona_context = _persona_gate(args.persona if args.persona else None)
    system_prompt = _load_system_prompt(None)
    if persona_context:
        system_prompt = persona_context + "\n\n---\n\n" + system_prompt
    writer = _session.SessionWriter(cwd=str(Path.cwd()))
    history: list[dict] = []

    _fire_session_start(writer.session_id)
    _grove.session_started(writer.session_id, model)

    trust_label = "trust=on" if args.trust else "trust=off"
    persona_label = f"  [persona:{args.persona}]" if args.persona else ""
    print(f"\nRatatosk  b17:L3178  [{model}]  [{trust_label}]{persona_label}  session:{writer.session_id[:8]}…")
    print("Type /exit, /status, /clear.\n")

    boot_ctx = _load_boot_context(os.environ.get("WILLOW_AGENT_NAME", "hanuman"))
    if boot_ctx:
        print(boot_ctx)
        print()

    while True:
        try:
            user_input = input("▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/status":
            print(f"  session : {writer.session_id}")
            print(f"  turns   : {len(history) // 2}")
            print(f"  jsonl   : {writer.path}")
            continue
        if user_input == "/clear":
            history = []
            print("  history cleared")
            continue
        if user_input.startswith("/"):
            print(f"  unknown command: {user_input}")
            continue

        _fire_prompt_submit(writer.session_id, user_input)
        writer.write_user(user_input)
        history.append({"role": "user", "content": user_input})

        try:
            if use_local:
                import requests
                messages = [{"role": "system", "content": system_prompt}] + history
                r = requests.post(
                    "http://localhost:11434/api/chat",
                    json={"model": model, "messages": messages, "stream": False},
                    timeout=120,
                )
                r.raise_for_status()
                text = r.json().get("message", {}).get("content", "")
                print(text)
                writer.write_assistant(text)
                history.append({"role": "assistant", "content": text})
            else:
                while True:
                    response_text = ""
                    with client.messages.stream(
                        model=model,
                        max_tokens=8192,
                        system=system_prompt,
                        messages=history,
                        tools=all_tools,
                    ) as stream:
                        for chunk in stream.text_stream:
                            print(chunk, end="", flush=True)
                            response_text += chunk
                        final = stream.get_final_message()

                    print()
                    assistant_content = final.message.content
                    writer.write_assistant(response_text)
                    history.append({"role": "assistant", "content": assistant_content})

                    tool_uses = [b for b in assistant_content if getattr(b, "type", None) == "tool_use"]
                    if not tool_uses:
                        history, compacted = _compact(history)
                        if compacted:
                            print(f"  [compacted — keeping last {_MAX_TURNS} turns]", flush=True)
                        break

                    tool_results = []
                    for tu in tool_uses:
                        result = _tools.prompt_and_dispatch(
                            tu.name, tu.input, args.trust, mcp_names, mcp_call
                        )
                        print(f"  [tool:{tu.name}] → {str(result)[:120]}", flush=True)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": str(result),
                        })
                    history.append({"role": "user", "content": tool_results})

        except Exception as e:
            print(f"\nERROR: {e}")
            continue

    turns = len(history) // 2
    _fire_stop(writer.session_id)
    if args.mcp:
        try:
            from ratatosk import mcp_client
            mcp_client.shutdown()
        except Exception:
            pass
    _grove.session_ended(writer.session_id, turns, str(writer.path))
    print(f"Session written: {writer.path}")


if __name__ == "__main__":
    main()
