"""
gatefirst.identity — check in, receive a capability.

check_in() does not return a boolean for functions to consult later. It
returns the only object through which storage is reachable, shaped by the
trust level at the door: a Rookie's handle has no add_person to call —
absent, not refused. dir(handle) is the policy document.

Same actors and trust ceilings as sap/core/gate.py: journal (the user,
Steady) and jeles (the LLM, Rookie).
"""

import secrets as _pysecrets
from pathlib import Path

from auth_gate import build_signed_header
from willow_gate import TRUST_LEVELS, WillowGate

from .store import Denied, Store

ROLES = {
    "journal": {"agent_id": "gatefirst-journal", "trust": 2,
                "tools": ("read", "write"), "pass_floor": 3},
    "jeles":   {"agent_id": "gatefirst-jeles", "trust": 1,
                "tools": ("read",), "pass_floor": 0},
}


def _signed_header(role, secret, *, nonce=None, timestamp=None, tools=None):
    spec = ROLES[role]
    return build_signed_header(
        agent_id=spec["agent_id"],
        agent_name=role,
        last_gate="the-squirrel-gatefirst",
        trust_level=spec["trust"],
        tools=list(spec["tools"] if tools is None else tools),
        secret=secret,
        pass_count=spec["pass_floor"],
        nonce=nonce,
        timestamp=timestamp,
    )


# ── The handles — capability, not check ──────────────────────────────────────

class ReadHandle:
    """What a read-only trust level gets: retrieval, nothing else."""

    def __init__(self, store, role, session):
        self._store = store
        self._role = role
        self._session = session

    def search_persons(self, name_query=""):
        return self._store.search_persons(name_query)

    def get_person(self, person_id):
        return self._store.get_person(person_id)

    def list_fragments(self, person_name=None):
        return self._store.list_fragments(person_name)


class WriteHandle(ReadHandle):
    """Read plus mutation. Minted only for writable sessions."""

    def add_person(self, **fields):
        return self._store.add_person(**fields)

    def add_fragment(self, **fields):
        return self._store.add_fragment(**fields)

    def link(self, fragment_id, person_id):
        return self._store.link(fragment_id, person_id)


class StewardHandle(WriteHandle):
    """Write plus export. The method exists only here — and it still clears
    authorize_tool(export=True) at the moment of use, so the ledger sees it."""

    def export_gedcom_text(self):
        return self._store.export_gedcom_text()


# ── The one door ─────────────────────────────────────────────────────────────

class Gatehouse:
    """Owns the WillowGate, mints per-process secrets, and exchanges a
    successful check-in for the largest handle the trust level allows."""

    def __init__(self, base_dir, db_path=":memory:"):
        self._gate = WillowGate(base_dir=Path(base_dir), require_pgp=False)
        self._db_path = str(db_path)
        self._secrets = {}
        for role, spec in ROLES.items():
            secret = _pysecrets.token_bytes(32)
            self._gate.register_agent(spec["agent_id"], secret, max_trust=spec["trust"])
            self._secrets[role] = secret

    @property
    def announcements(self):
        log = self._gate.announcements_log
        return log.read_text() if log.exists() else ""

    def check_in(self, role):
        if role not in ROLES:
            raise Denied(f"unknown actor {role!r} — one of {sorted(ROLES)}")
        ok, msg, session = self._gate.check_in(
            _signed_header(role, self._secrets[role]))
        if not ok or session is None:
            raise Denied(f"check-in refused for {role!r}: {msg}")
        store = Store(self._gate, session, self._db_path)
        level = TRUST_LEVELS[session["trust_level"]]
        if session["writable"] and level.write_export_allowed:
            cls = StewardHandle
        elif session["writable"]:
            cls = WriteHandle
        else:
            cls = ReadHandle
        return cls(store, role, session)

    def check_out(self, handle):
        """Close the handle's session; writes the exit diff to the ledger."""
        session = handle._session
        if session["nonce"] not in self._gate.sessions:
            return
        exit_header = _signed_header(
            handle._role, self._secrets[handle._role],
            nonce=session["nonce"],
            timestamp=max(int(time.time() * 1000), session["entry_ms"] + 1),
            tools=sorted(session["tools_used"]))
        self._gate.check_out(session, exit_header)
