"""
tools.py — Tool definitions and dispatch for the Ratatosk tool loop.
b17: 0CE44  ΔΣ=42
"""
import json
import shlex
import subprocess
from pathlib import Path

BASH_TOOL = {
    "name": "Bash",
    "description": (
        "Run a command without a shell (POSIX words via shlex). "
        "No pipes/redirection unless you invoke `bash`/`sh` as the executable "
        "(e.g. `[\"bash\",\"-lc\",\"git status | head\"]`) — prefer simple argv forms."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
        },
        "required": ["command"],
    },
}

READ_TOOL = {
    "name": "Read",
    "description": "Read a file from disk and return its contents (up to 4000 chars).",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
        },
        "required": ["file_path"],
    },
}

BASE_TOOLS = [BASH_TOOL, READ_TOOL]

_MAX_READ = 4000
_BASH_TIMEOUT = 60


def dispatch(name: str, inputs: dict, mcp_names: set, mcp_call) -> object:
    if name == "Bash":
        cmd = inputs.get("command", "")
        try:
            argv = shlex.split(cmd, posix=True)
        except ValueError as e:
            return f"ERROR: could not parse command: {e}"
        if not argv:
            return "(no command)"
        try:
            result = subprocess.run(
                argv, shell=False, capture_output=True, text=True, timeout=_BASH_TIMEOUT
            )
            return (result.stdout + result.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"ERROR: command timed out ({_BASH_TIMEOUT}s)"
        except Exception as e:
            return f"ERROR: {e}"

    if name == "Read":
        path = inputs.get("file_path", "") or inputs.get("path", "")
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")[:_MAX_READ]
        except Exception as e:
            return f"ERROR: {e}"

    if name in mcp_names and mcp_call is not None:
        return mcp_call(name, inputs)

    return f"[stub] tool '{name}' not wired. inputs={json.dumps(inputs)[:120]}"


def prompt_and_dispatch(name: str, inputs: dict, trusted: bool,
                        mcp_names: set, mcp_call) -> object:
    if not trusted:
        summary = json.dumps(inputs, ensure_ascii=False)[:200]
        print(f"\n  [tool:{name}] {summary}")
        try:
            answer = input("  Allow? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "y":
            return json.dumps({"error": "user denied"})
    return dispatch(name, inputs, mcp_names, mcp_call)
