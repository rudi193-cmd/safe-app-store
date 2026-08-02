"""The disposition log: append-only, reasoned both ways, never overwritten.

Three properties this module exists to hold:

**A reason is required to grant, not only to refuse.** Every app store on earth
logs installs and none of them logs why. A grant with no reason is the same
shape as no decision at all, six months later.

**Absence is a recorded value.** A request that was refused, and a request that
expired unanswered, are rows. "No row" means something else entirely: nobody
ever asked. Conflating those is how a log starts lying.

**Corrections land beside the record, never on top of it.** Nothing here
mutates a prior line. A decision that later looks wrong stays legible as what it
was — a reasonable call made on the evidence available at the time — and the
evidence available at the time is copied into the row precisely so that question
can be asked later.

That last one is why each answer snapshots the app's interruption record as it
stood at the instant of the decision. The catalog will change: someone will
measure an app that was `assumed`, or a new build will demote a `measured`
record. A log holding only the current value can confirm the present state but
cannot be used to check whether the reasoning was sound.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .interruption import Interruption

OPEN = "open"
GRANTED = "granted"
REFUSED = "refused"
EXPIRED = "expired"

INSTALL_OK = "installed"
INSTALL_FAILED = "install_failed"

#: Rows are appended, never rewritten. A later row about the same request_id
#: supersedes an earlier one for the purpose of "current state" without
#: destroying it.
KIND_REQUEST = "request"
KIND_ANSWER = "answer"
KIND_INSTALL = "install"


class DispositionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Log:
    """An append-only JSONL disposition log.

    `clock` and `new_id` are injectable so the tests can assert on exact rows
    rather than on whatever the wall clock happened to say.
    """

    path: Path
    roster: "tuple[str, ...]"
    clock = staticmethod(_now)
    new_id = staticmethod(lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        if not self.roster:
            raise DispositionError("roster is empty; there is nobody who can ask")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- writing -----------------------------------------------------------

    def _append(self, row: dict) -> dict:
        row["at"] = self.clock().isoformat()
        line = json.dumps(row, sort_keys=True)
        # Append-and-fsync rather than read-modify-write: there is no code path
        # in this module that can truncate the file.
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return row

    def request(self, subject_id: str, app_id: str, asked_by: str,
                within_hours: int = 48) -> dict:
        """A child asks for an app.

        `subject_id` must be on the roster. The UI offers a fixed list rather
        than a text box: a consent log whose subject is a name the requester
        typed records an assertion, not an identity.
        """
        if subject_id not in self.roster:
            raise DispositionError(
                f"subject {subject_id!r} is not on the roster {list(self.roster)}"
            )
        if not asked_by.strip():
            raise DispositionError("asked_by is empty")
        if within_hours <= 0:
            raise DispositionError("within_hours must be positive")

        due_by = (self.clock() + timedelta(hours=within_hours)).isoformat()
        return self._append({
            "kind": KIND_REQUEST,
            "request_id": self.new_id(),
            "subject_id": subject_id,
            "app_id": app_id,
            "asked_by": asked_by.strip(),
            "due_by": due_by,
            "disposition": OPEN,
        })

    def answer(self, request_id: str, granted: bool, by: str, reason: str,
               interruption: Interruption | None = None) -> dict:
        """A parent grants or refuses, with a reason, either way."""
        if not by.strip():
            raise DispositionError("answering parent is unnamed")
        if not reason.strip():
            raise DispositionError(
                "a reason is required to grant as well as to refuse; a grant "
                "with no reason is indistinguishable from no decision"
            )
        current = self.current(request_id)
        if current is None:
            raise DispositionError(f"no such request {request_id!r}")
        if current["disposition"] != OPEN:
            raise DispositionError(
                f"request {request_id} is already {current['disposition']}; "
                "append a new request rather than re-answering this one"
            )

        row = {
            "kind": KIND_ANSWER,
            "request_id": request_id,
            "disposition": GRANTED if granted else REFUSED,
            "by": by.strip(),
            "reason": reason.strip(),
        }
        if interruption is not None:
            # The evidence as it stood at the moment of the decision, not as it
            # stands whenever someone reads the log.
            row["interruption_at_decision"] = interruption.to_json()
        return self._append(row)

    def record_install(self, request_id: str, ok: bool, detail: str) -> dict:
        """Record an install attempt — including, especially, a failed one.

        A grant that never resulted in an install and a grant that installed
        cleanly are different facts. Leaving the failure unwritten would make
        the log agree with the optimistic reading by default.
        """
        return self._append({
            "kind": KIND_INSTALL,
            "request_id": request_id,
            "disposition": INSTALL_OK if ok else INSTALL_FAILED,
            "detail": detail,
        })

    # -- reading -----------------------------------------------------------

    def rows(self) -> "list[dict]":
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def current(self, request_id: str) -> "dict | None":
        """The folded state of one request. The rows behind it stay on disk."""
        state: dict | None = None
        for row in self.rows():
            if row.get("request_id") != request_id:
                continue
            if state is None:
                state = dict(row)
            else:
                state.update({k: v for k, v in row.items() if k != "kind"})
        if state is None:
            return None
        if state["disposition"] == OPEN and self._is_overdue(state):
            # Expiry is derived, not written, so that an unanswered request
            # cannot silently become an answered one on disk.
            state = dict(state, disposition=EXPIRED)
        return state

    def _is_overdue(self, state: dict) -> bool:
        due = state.get("due_by")
        if not due:
            return False
        return datetime.fromisoformat(due) < self.clock()

    def open_requests(self) -> "list[dict]":
        ids = [r["request_id"] for r in self.rows() if r.get("kind") == KIND_REQUEST]
        out = []
        for request_id in ids:
            state = self.current(request_id)
            if state and state["disposition"] == OPEN:
                out.append(state)
        return out

    def history(self, request_id: str) -> "list[dict]":
        """Every row for one request, oldest first — the audit view.

        `current()` answers what the state is. This answers how it got there,
        which is the question a fold cannot be asked.
        """
        return [r for r in self.rows() if r.get("request_id") == request_id]
