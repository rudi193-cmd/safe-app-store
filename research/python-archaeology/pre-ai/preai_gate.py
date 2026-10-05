"""Provenance gate: every added line in a diff must exist, verbatim apart from
leading whitespace, in the pre-AI CPython snapshot (last commit before GitHub
Copilot's preview, 2021-06-29).

usage: git diff | python3 preai_gate.py /path/to/cpython-preai
Exit 0 if every added line has a pre-AI origin, 1 otherwise.
"""
import os
import sys

PRE_ROOT = sys.argv[1]


def index_tree(root):
    seen = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if not name.endswith((".py", ".c", ".h", ".rst", ".txt")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        key = line.strip()
                        if key and key not in seen:
                            seen[key] = f"{os.path.relpath(path, root)}:{lineno}"
            except OSError:
                pass
    return seen


def added_lines(diff_text):
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            yield line[1:]


seen = index_tree(PRE_ROOT)
failures = 0
for line in added_lines(sys.stdin.read()):
    key = line.strip()
    if not key:
        continue
    origin = seen.get(key)
    if origin is None:
        failures += 1
        print(f"NO PRE-AI ORIGIN  {line}")
    else:
        print(f"{origin:<45} {line}")
print(f"\n{failures} line(s) without pre-AI origin")
sys.exit(1 if failures else 0)
