#!/usr/bin/env python3
"""stores/instrument_callgraph.py — the measuring panel's first REAL fleet
instrument: `codebase-memory-mcp`'s call graph (docs/design/the-forge-measure.md).

The box's decoy — `login.php`'s `check_login()`, retrieved by every ranker as
"where auth lives," and never actually called — was caught by exactly one kind
of tool: one that traced the CALL GRAPH (`fan_in=0`) instead of ranking by
appearance. `codebase-memory-mcp` is that tool (rule 11: reuse it, don't rebuild
a tree-sitter graph). This adapter drives it one-shot via its `cli --json`
surface, finds functions with no callers, and emits a per-file `Finding` the
panel can converge with `census`/`hygiene` — a dead function in a file that is
ALSO an accidental commit is a much louder signal than either alone.

**Dead code = set difference, not a broken OPTIONAL-count.** codebase-memory's
query engine returns `count(a)=1` for an OPTIONAL MATCH that matched nothing
(verified), so fan_in can't be read from one aggregate. Instead: all functions
MINUS the targets of any `CALLS` edge, minus entry points (a genuine root is
not dead) and language builtins. That set difference is the pure, tested core
(`_dead_functions`); the subprocess plumbing around it degrades to
`InstrumentUnavailable` on any failure (binary absent, non-zero exit, unpardable
output) — the panel's honest-coverage path, never a crash.

Not in the panel's dependency-free DEFAULT_INSTRUMENTS: this needs the external
binary (downloaded on first use, runs a daemon), so a caller opts in
(`measure_panel` CLI `--with-callgraph`, or pass `CallGraphInstrument()`
explicitly). When it is NOT included, the panel names `call-graph` as an
uncovered class — the sigmap honesty.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_mp_spec = importlib.util.spec_from_file_location("measure_panel", _REPO / "stores" / "measure_panel.py")
measure_panel = importlib.util.module_from_spec(_mp_spec)
sys.modules["measure_panel"] = measure_panel
_mp_spec.loader.exec_module(measure_panel)

Finding = measure_panel.Finding
InstrumentUnavailable = measure_panel.InstrumentUnavailable

_DEFAULT_BINARY = "codebase-memory-mcp"

# Column order matters — the pure parser splits on it. `qn` and `entry` never
# contain spaces; `file_path` might, so it is LAST and split with maxsplit.
_Q_ALL = "MATCH (f:Function) RETURN f.qualified_name AS qn, f.is_entry_point AS entry, f.file_path AS file"
_Q_CALLED = "MATCH (a)-[:CALLS]->(f:Function) RETURN f.qualified_name AS qn"


# ── the pure core (unit-tested without the binary) ──────────────────────────

def _data_rows(text: str) -> list[str]:
    """The indented data rows of codebase-memory's text table, dropping its
    `rows:`/`(cols …)` header and `total:` footer."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("rows:") or s.startswith("total:") or s.startswith("(cols"):
            continue
        out.append(s)
    return out


def _dead_functions(all_text: str, called_text: str) -> list[tuple[str, str]]:
    """`(qualified_name, file_path)` for every function with no caller — the
    set difference `all_functions - called - entry_points - builtins`. Pure:
    takes the two query result texts, returns the dead set. `entry` is the
    quoted `"true"`/`"false"` codebase-memory prints."""
    called = set(_data_rows(called_text))  # each row is a bare qualified_name
    dead: list[tuple[str, str]] = []
    for row in _data_rows(all_text):
        parts = row.split(None, 2)  # qn, entry, file (file last — may contain spaces)
        if len(parts) < 3:
            continue
        qn, entry, file = parts[0], parts[1].strip('"'), parts[2]
        if qn in called:
            continue                    # it has a caller — not dead
        if entry == "true":
            continue                    # a genuine entry point is not "dead"
        if qn.startswith("builtins.") or file.startswith("<"):
            continue                    # language builtins, not the build's code
        dead.append((qn, file))
    return dead


# ── the instrument ──────────────────────────────────────────────────────────

class CallGraphInstrument:
    """Drives `codebase-memory-mcp` to flag dead code (`fan_in=0`). `covers` the
    `call-graph` class. Raises `InstrumentUnavailable` for any environmental
    failure so the panel records a coverage gap rather than crashing."""

    name = "call-graph"
    covers = "call-graph"

    def __init__(self, binary: str = _DEFAULT_BINARY, timeout: float = 180.0):
        self.binary = binary
        self.timeout = timeout

    def measure(self, build_dir: Path) -> list["Finding"]:
        exe = shutil.which(self.binary) or (self.binary if Path(self.binary).exists() else None)
        if exe is None:
            raise InstrumentUnavailable(
                f"codebase-memory-mcp not found ({self.binary!r}); `pip install codebase-memory-mcp`"
            )
        build_dir = Path(build_dir)
        project = None
        try:
            idx = self._call(exe, "index_repository", {"repo_path": str(build_dir)})
            project = (idx.get("structuredContent") or {}).get("project")
            if not project:
                raise InstrumentUnavailable(f"index_repository returned no project: {idx!r}")
            all_text = self._query_text(exe, project, _Q_ALL)
            called_text = self._query_text(exe, project, _Q_CALLED)
        except InstrumentUnavailable:
            raise
        except Exception as e:  # noqa: BLE001 — any drive failure is a coverage gap, not a crash
            raise InstrumentUnavailable(f"codebase-memory-mcp drive failed: {type(e).__name__}: {e}") from e
        finally:
            if project:
                self._call(exe, "delete_project", {"project": project}, tolerant=True)

        out: list[Finding] = []
        for qn, file in _dead_functions(all_text, called_text):
            out.append(Finding(
                instrument=self.name, artifact=file, metric="fan_in", value=0, severity="med",
                detail=f"{qn} has no callers (fan_in=0) — dead code the ranker would still 'find'; the box's decoy",
            ))
        return out

    # -- subprocess plumbing --------------------------------------------------

    def _call(self, exe: str, tool: str, args: dict, *, tolerant: bool = False) -> dict:
        try:
            proc = subprocess.run(
                [exe, "cli", "--json", tool, json.dumps(args)],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            if tolerant:
                return {}
            raise InstrumentUnavailable(f"{tool} failed to run: {e}") from e
        for line in reversed(proc.stdout.splitlines()):  # last JSON line; skip log/hint lines
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    break
                if d.get("isError") and not tolerant:
                    raise InstrumentUnavailable(f"{tool} error: {d.get('structuredContent') or d.get('content')}")
                return d
        if tolerant:
            return {}
        raise InstrumentUnavailable(f"{tool}: no JSON in output (exit {proc.returncode})")

    def _query_text(self, exe: str, project: str, query: str) -> str:
        d = self._call(exe, "query_graph", {"project": project, "query": query})
        content = d.get("content") or [{}]
        return content[0].get("text", "") if content else ""


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(prog="instrument_callgraph.py")
    p.add_argument("build_dir")
    p.add_argument("--binary", default=_DEFAULT_BINARY)
    a = p.parse_args()
    for f in CallGraphInstrument(binary=a.binary).measure(Path(a.build_dir)):
        print(f"{f.artifact}: {f.detail}")
