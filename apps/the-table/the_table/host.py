"""host.py -- where a script that runs a session finds the one-script (flatten F2).

The record is the one chain (willows-grove
``docs/design/one-script/flatten-2026-10-19.md`` F-1), and until the game
pieces move into willow-bot (F4) it lives beside the-table, not in it. The
operator chose how a script reaches it (F-7, "1 B"): it finds the one-script
beside it, the way the-table already reaches ``apps/bureau``, ``apps/game``
and ``apps/game-lab`` -- a ``sys.path`` shim. This module is that shim.

Only the scripts that RUN a session import it (``proof.py``,
``aetheris5e/sealed_run.py``, ``gm5e.py``, ``combat.py``). The library
modules (``onescript_sink.py``, the adapters, ``gm.py``) still take a writer
handed in and import no onescript. At F4 this file goes: the imports become
plain package imports.

Where it looks:

  one-script   ``$ONESCRIPT_HOME``, else ``<repos>/willow-bot/one-script``
  the law      ``$ONESCRIPT_GROVE``, else ``<repos>/willows-grove``

``<repos>`` is the directory holding safe-app-store. Two states, never
collapsed: ``reachable``, or ``unreachable`` with why (no one-script, no law,
or the one-script would not import). A script that cannot reach it says so and
exits 2; it never falls back to a chain of its own.

A ``Box`` is a one-script box with its keys file beside it, never inside
(the one-script refuses that). Its ``desk`` and ``table`` keys are made here,
fresh, from ``os.urandom``: they are the box's code identities. No human key
is made, read or held here; a seal is the human's, with their own key, through
the one-script.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_REPOS = Path(__file__).resolve().parents[4]  # the_table -> the-table -> apps -> safe-app-store -> repos

#: Exit code for "the one-script is not reachable": said, not a failure of the game.
UNREACHABLE = 2


class Unreachable(RuntimeError):
    """The one-script, or the law it reads, is not beside the-table."""


def where() -> dict:
    """Where the one-script and the law are looked for."""
    home = os.environ.get("ONESCRIPT_HOME")
    grove = os.environ.get("ONESCRIPT_GROVE")
    return {
        "onescript": Path(home).expanduser() if home else _REPOS / "willow-bot" / "one-script",
        "grove": Path(grove).expanduser() if grove else _REPOS / "willows-grove",
    }


def reach() -> dict:
    """``{"state": "reachable", "onescript", "grove"}`` or
    ``{"state": "unreachable", "why"}``."""
    w = where()
    if not (w["onescript"] / "onescript" / "record.py").is_file():
        return {"state": "unreachable",
                "why": f"no one-script at {w['onescript']} (set ONESCRIPT_HOME)"}
    if not (w["grove"] / "governance" / "CONSTITUTION.md").is_file():
        return {"state": "unreachable",
                "why": f"no law: willows-grove's constitution isn't at {w['grove']} "
                       "(set ONESCRIPT_GROVE)"}
    return {"state": "reachable", **w}


def onescript() -> SimpleNamespace:
    """The one-script modules a host needs (api, record, table). Raises
    ``Unreachable`` (with why) when it is not beside."""
    got = reach()
    if got["state"] != "reachable":
        raise Unreachable(got["why"])
    home = str(got["onescript"])
    if home not in sys.path:
        sys.path.insert(0, home)
    try:
        mods = {m: importlib.import_module(f"onescript.{m}") for m in ("api", "record", "table")}
    except ImportError as e:
        raise Unreachable(f"the one-script at {home} would not import: {e}") from e
    return SimpleNamespace(grove=got["grove"], **mods)


class Box:
    """One one-script box, checked in, and the table's writer onto it.

    ``Box()`` is a throwaway box in a temp dir, removed by ``close()``.
    ``Box(path)`` keeps ``<path>/box`` and ``<path>/keys/keys.json`` across
    runs (``gm5e.py`` writes one campaign over many processes); the keys are
    made once, the first time, 0600 in a 0700 directory beside the box."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.os = onescript()
        self._temp = path is None
        self.dir = Path(tempfile.mkdtemp(prefix="the-table-box-") if path is None else path)
        keys = self.dir / "keys" / "keys.json"
        if not keys.exists():
            keys.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(keys, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"desk": os.urandom(32).hex(), "table": os.urandom(32).hex()}, f)
        grove = self.os.grove
        self.cfg = self.os.api.Config(
            box=self.dir / "box", keys=keys,
            constitution=grove / "governance" / "CONSTITUTION.md",
            ci=grove / ".github" / "workflows" / "tests.yml",
            root=self.dir / "no-clone", grove=grove, venv=self.dir / "no-venv",
            no_tests=True, phone=True, store=False,
        )
        got = self.os.api.checkin(self.cfg)
        if got.get("code") != 0:
            raise Unreachable(f"the box would not check in: {got.get('refused') or got.get('wont_open') or got}")

    # -- writing ---------------------------------------------------------------
    def write(self, row: dict) -> dict:
        """One code-written ``verdict`` row, as the box's ``table`` identity."""
        return self.os.table.verdict(self.cfg, row)

    def sink(self, **kw: Any):
        """A ``OneScriptSink`` writing to this box, checking beat seals here."""
        from .onescript_sink import OneScriptSink

        return OneScriptSink(self.write, check=self.beat_seal, **kw)

    def propose(self, pending: dict, cites: list) -> dict:
        """A decision beat as a proposal the human seals (one-script's
        ``table.propose_beat``). Code never seals it."""
        return self.os.table.propose_beat(self.cfg, pending, cites)

    def beat_seal(self, subject: str) -> dict:
        return self.os.table.beat_seal(self.cfg, subject)

    # -- reading ---------------------------------------------------------------
    @property
    def record_path(self) -> Path:
        return self.cfg.box / "record.jsonl"

    def rows(self) -> list[dict]:
        return [json.loads(x) for x in self.record_path.read_text().splitlines() if x.strip()]

    def verify(self, box: str | os.PathLike | None = None) -> list[str]:
        """Every break in the chain and its sealed tip, read with no write
        token (one-script's own ``verify_chain`` and ``verify_anchor``). Empty
        means it holds. ``box`` reads another box dir (a tampered copy) against
        this box's anchor."""
        rec = self.os.record.Record(
            Path(box) if box is not None else self.cfg.box, lambda: "", "", object(),
            anchor=self.cfg.keys.parent / self.os.api.ANCHOR,
        )
        return rec.verify_chain() + rec.verify_anchor(None)

    def head(self) -> str | None:
        rows = self.rows()
        return rows[-1]["hash"] if rows else None

    def tampered_copy(self, edit) -> Path:
        """A copy of the box with ``edit(rows) -> rows`` applied to its record,
        written back as JSON lines (the hashes left as they were), for a
        script to show the chain refusing it. The original is untouched."""
        copy = Path(tempfile.mkdtemp(prefix="the-table-tampered-")) / "box"
        shutil.copytree(self.cfg.box, copy)
        rows = edit(self.rows())
        (copy / "record.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return copy

    def close(self) -> None:
        if self._temp:
            shutil.rmtree(self.dir, ignore_errors=True)

    def __enter__(self) -> Box:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class StateSink:
    """The three sink methods for a script whose steps are free-form states
    (aetheris5e's d20 checks, attacks, saves), not 2d6 rolls: each call is one
    ``verdict`` row carrying the state as given, under ``state``. A step is
    ``what: step`` (a d20 check is not a 2d6 roll, and is never read as one)."""

    def __init__(self, box: Box, game: str) -> None:
        self.box, self.game = box, game
        self.session: str | None = None
        self.rows: list[dict] = []

    def _emit(self, what: str, reason: str, state: dict) -> dict:
        if self.session is None:
            raise RuntimeError("open_session first")
        row = {"what": what, "session": self.session, "game": self.game,
               "verdict": what, "reason": reason, "state": state}
        res = self.box.write(row)
        if not isinstance(res, dict) or res.get("code") != 0 or "row" not in res:
            from .onescript_sink import SinkRefused

            raise SinkRefused(f"one-script refused the {what} row: "
                              f"{(res or {}).get('refused', res)!r}")
        self.rows.append(res["row"])
        return res["row"]

    def open_session(self, session_id: str, meta: dict) -> None:
        self.session = str(session_id)
        self._emit("open", f"session {self.session} opened", dict(meta))

    def resume(self, session_id: str) -> None:
        """Carry on a session another process opened (gm5e's commands)."""
        self.session = str(session_id)

    def snapshot(self, state: dict, note: str = "") -> None:
        self._emit("step", note, dict(state))

    def close_session(self, result: dict) -> None:
        self._emit("result", str(result.get("summary") or result.get("outcome") or ""), dict(result))

    def decision(self, pending: dict) -> str:
        """A decision beat: one ``decision`` verdict row, then the beat handed
        to the one-script as a proposal (``Box.propose``) citing that row.
        Returns the proposal's subject; only the human's seal makes it count,
        and code never writes that seal."""
        row = self._emit("decision", "a decision beat: the human seals it",
                         {"fact_id": pending["fact_id"], "fact": pending.get("fact")})
        res = self.box.propose(pending, [row["hash"]])
        if not isinstance(res, dict) or res.get("code") != 0 or "subject" not in res:
            from .onescript_sink import SinkRefused

            raise SinkRefused(f"the beat was not proposed: {(res or {}).get('refused', res)!r}")
        return res["subject"]


def box_or_exit(path=None) -> Box:
    """A ``Box``, or, when the one-script is not beside, the reason on stderr
    and ``SystemExit(2)``."""
    try:
        return Box(path)
    except Unreachable as e:
        print(f"the one-script is unreachable: {e}", file=sys.stderr)
        raise SystemExit(UNREACHABLE) from e
