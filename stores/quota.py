#!/usr/bin/env python3
"""stores/quota.py — per-builder fairness quotas (D6, docs/design/the-forge.md).

D6 names three things tenancy needs. Two are closed elsewhere: the Kart
working-directory/mount-boundary restriction
(`apps/the-forge/src/the_forge/mount_policy.py`) and store-native session
tokens for a resolved `builder_id` (`stores/session.py`). This module is the
third, named plainly in D6's own text: "Per-builder quotas layered on top of
Kart's existing per-*task* caps (2G mem, 512 PIDs already enforced) —
concurrent builds, sandbox-seconds budget — so the isolation Kart already
gives one task extends to fairness across many builders sharing the host."

Kart already caps what ONE build can do — memory and PID limits enforced
per-task by `kartikeya.sandbox._resource_limits`/`_limits_context`, at cgroup
or `prlimit` granularity. This module does not touch or duplicate any of
that. What Kart's per-task caps do NOT do is stop one builder from starting
an unbounded number of those already-capped tasks at once, or from
accumulating unbounded cumulative sandboxed execution time — either one lets
a single builder starve every other builder sharing this host, without ever
tripping a single task's own resource ceiling. This module is a lease-based
accounting layer that closes that gap: `acquire_build_slot`/
`release_build_slot` enforce a per-builder concurrent-build ceiling,
`record_build_duration`/`sandbox_seconds_used` track cumulative sandboxed
time so an optional budget can be enforced against it.

Store-side authority (D1), same directory and same trust level as
`principal.py`, `session.py`, and `checkpoint_memory.py`: a sandboxed build
has no business deciding its own resource entitlement — that is fairness
policy, and D1 puts all policy on the store's side of the trust boundary, not
inside `apps/the-forge/`, which never imports this module.

**Storage shape — one JSON file per `builder_id`, one coarse `flock` over the
whole store.** Two axes, decided independently, mirroring different parts of
this module family for different reasons:

  * *One file per builder* (not a single shared index file with one row per
    builder plus one row per lease) — the same directory-per-builder shape
    `checkpoint_memory.py` uses, though for a different reason than that
    module's cross-builder-leak argument (this data is not in that
    sensitivity class — quota numbers, not calibration/trust state). Here
    the reason is operational simplicity and blast-radius: every operation
    this module performs (acquire, release, record a duration, read a
    balance) is already scoped to exactly one `builder_id`, so a file that
    is *itself* scoped to one `builder_id` means an operation never has to
    parse, and a corruption can never touch, any other builder's rows. A
    shared index file would need a second key (`builder_id`) inside every
    row and careful filtering on every read the file-per-builder layout
    gets for free from its own path.
  * *One coarse lock for the whole store*, not a per-builder lock file —
    this is the OPPOSITE choice from "one file per builder" on the
    isolation axis, and deliberately so: it is the exact locking shape
    `principal.py._locked`/`session.py._locked` already use ("a lock that
    is obviously correct beats a clever scheme that is subtly not"), copied
    here rather than re-derived, because the correctness property this
    module needs — no two concurrent `acquire_build_slot` calls for the
    same builder can both observe "one slot free" and both take it — is
    exactly the check-then-increment race `principal.py`'s own docstring
    names, and a coarse lock closes it with the same one proof this family
    already leans on everywhere else. A per-builder lock file would also
    close that race (and allow unrelated builders to proceed concurrently),
    but it is a second locking primitive this module family has not needed
    anywhere else, for a throughput concern this dev-only store was never
    trying to solve. Not free — a burst of unrelated builders all calling
    `acquire_build_slot` at once serializes through one lock — but this
    store is explicitly DEV-ONLY (see `FilesystemQuotaStore`'s own
    docstring) and a real backing store is where that tradeoff gets
    revisited, the same disclaimer `principal.py`/`session.py` already
    carry for their own coarse locks.

**Crash recovery is the reason this has a TTL, not an afterthought bolted on
after the concurrency limit worked.** A build's process can die — OOM-killed,
host restart, the calling process itself crashing — without ever calling
`release_build_slot`. Modeled the same way `session.py` models session
expiry: every lease carries an `expires_at`, checked against a real clock AT
ACQUIRE TIME (not by a background reaper — there is no reaper process in this
module, matching `session.py`'s own "no expiry-driven cleanup" dev-store
disclaimer), so an abandoned lease simply stops counting against its
builder's concurrency limit once its TTL elapses, with no process needing to
notice the crash happened at all. `DEFAULT_LEASE_TTL_SECONDS` (below) is
picked deliberately longer than `apps/the-forge/src/the_forge/sandbox_runner.py`'s
own `DEFAULT_TIMEOUT_S` (120s) — see that constant's own comment for the
reasoning — so a slow-but-healthy build never gets treated as abandoned while
it is still legitimately running.

**Cumulative sandbox-seconds: a running total is the primitive; a rolling
window is a real, not-deferred, filter on top of it.** Every
`record_build_duration` call appends one `(elapsed_seconds, recorded_at)`
record to the builder's own file — not just a single incrementing counter —
specifically so `sandbox_seconds_used`'s `window_seconds` parameter can be a
real filter over real per-event timestamps (`sum of records with
recorded_at >= now - window_seconds`) rather than a documented-but-unbuilt
placeholder. `window_seconds=None` (the default) sums every record ever
recorded for that builder — the running total, and per the design doc's own
framing "the simpler primitive and probably the right default" — so a caller
that never asks for a window gets the simple behaviour for free, and a
caller that does gets the real thing, not a stub. The one honest cost of
keeping full history instead of a single counter: a builder's file grows by
one small record per completed build, forever, with nothing in this
dev-only module that ever trims it — the same "no expiry-driven cleanup"
disclaimer `session.py` already carries for its own rows, now true here too.

**A released lease is deleted, not tombstoned — the opposite of
`session.py`'s `revoked_at` choice, and deliberately so.** `session.py`'s
docstring explains why a revoked session keeps its row: a future caller
might need to know *why* a bearer token was refused, and revoking twice must
be idempotent without losing the first revocation's timestamp. Neither
reason applies to a lease: nothing downstream ever needs to explain why a
concurrency slot is free, and idempotency for `release_build_slot` on an
already-released or unknown lease is satisfied just as well by "no-op,
nothing to remove" as by "no-op, already marked" (see `release_lease`'s own
docstring). The concurrency question this module exists to answer is always
"how many leases are active RIGHT NOW" — a released lease is not part of
that answer ever again, so keeping it around after release would only be
dead weight with no caller that reads it.

Not in scope, deliberately — the boundary this module stops at:
  * Wiring `acquire_build_slot`/`release_build_slot`/`record_build_duration`
    into `apps/the-forge/src/the_forge/sandbox_runner.py` or
    `mount_policy.py`, or anywhere under `apps/the-forge/` at all. This
    module is the accounting primitive only — the same boundary
    `session.py` draws around itself relative to the OAuth handshake that
    would call it. See `docs/design/the-forge.md`'s D6 section for the
    dated note on what remains open.
  * The concurrency limit and sandbox-seconds budget NUMBERS
    (`DEFAULT_MAX_CONCURRENT_BUILDS`, and the fact that no default sandbox-
    seconds budget is enforced at all unless a caller opts in) are
    placeholders picked to have *some* sane default to test against, not a
    considered product/capacity decision — see each constant's own comment.
  * A background reaper that proactively frees abandoned leases before the
    next `acquire_build_slot` call happens to notice. Expiry is checked
    lazily, at read/acquire time, the same choice `session.py` already
    makes for its own token expiry.
  * Deciding whether a builder is even allowed to build at all (suspension,
    banning) — same "mechanics, not admission policy" boundary
    `session.py`'s own docstring draws for `mint_session`.

Usage (dev CLI, mirroring principal.py / session.py / checkpoint_memory.py's
shape):
    python stores/quota.py acquire <builder_id> [--max-concurrent N] [--lease-ttl-seconds S]
    python stores/quota.py release <builder_id> <lease_id>
    python stores/quota.py record <builder_id> <elapsed_seconds>
    python stores/quota.py used <builder_id> [--window-seconds S]
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import secrets
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

DEFAULT_QUOTA_ROOT = Path(__file__).resolve().parent / ".quotas"

# Placeholder, not a considered product decision (see module docstring's
# "Not in scope" section and docs/design/the-forge.md's D6 note) — some
# sane default is needed so acquire_build_slot has one when a caller does
# not override it, and 2 is small enough to make the concurrency tests in
# this module's own test suite fast without special-casing. A real capacity
# number depends on host sizing this module has no visibility into.
DEFAULT_MAX_CONCURRENT_BUILDS = 2

# apps/the-forge/src/the_forge/sandbox_runner.py's own DEFAULT_TIMEOUT_S is
# 120 seconds — the hard ceiling `run_in_sandbox` enforces on one build by
# default (a caller can still pass a longer per-task timeout; this module
# has no visibility into that override at acquire time, which is exactly
# why the default here needs real margin, not just "greater than 120").
# 300s (5 minutes) leaves room for: the 120s the sandboxed command itself
# may legitimately run, queueing/startup time before the sandboxed command
# starts, and processing time after it exits but before the caller gets
# around to calling release_build_slot in its own finally block — while
# still bounding how long a genuinely orphaned lease (crash, OOM-kill, host
# restart) can squat on a concurrency slot before this module's own expiry
# check (not a background reaper — see module docstring) recovers it on the
# next acquire attempt. A caller running longer builds should pass its own
# lease_ttl_seconds rather than rely on this default being large enough.
DEFAULT_LEASE_TTL_SECONDS = 300.0

# 128 bits, same shape and same reasoning as principal.py's
# _BUILDER_ID_BYTES / session.py's _TOKEN_BYTES sizing convention: enough
# entropy that two callers can never mint the same lease_id, nothing more
# derived from it than that.
_LEASE_ID_BYTES = 16

# principal.py is loaded the same way session.py and checkpoint_memory.py
# already load it — spec_from_file_location, not a package-relative import,
# because stores/ has no __init__.py and is run as a directory of
# standalone scripts, not installed as a package. _check_builder_id is
# imported directly rather than re-implemented: principal.py is the one
# place a builder_id's path-safety charset is defined, and re-deriving that
# rule here would be exactly the kind of drift session.py's own docstring
# warns against.
_REPO = Path(__file__).resolve().parent.parent
_principal_spec = importlib.util.spec_from_file_location(
    "principal", Path(__file__).resolve().parent / "principal.py"
)
principal = importlib.util.module_from_spec(_principal_spec)
sys.modules["principal"] = principal
_principal_spec.loader.exec_module(principal)

_principal_check_builder_id = principal._check_builder_id


class QuotaError(Exception):
    """Fail-closed refusal — bad builder_id/parameters, a store that did not
    honor its own contract, or an inconsistent store. Every refusal in this
    module raises; nothing returns a bool a caller could forget to check."""


class QuotaExceededError(QuotaError):
    """`acquire_build_slot`'s fail-closed refusal: this builder is already
    at `max_concurrent` non-expired leases, or (only if a budget was
    configured) at or over their cumulative sandbox-seconds budget. Carries
    the numbers that produced the refusal — mirroring `principal.py`'s
    `AuthenticatorConflict.existing` / `checkpoint_memory.py`'s
    `CheckpointConflict`/`CheckpointRejected` shape of "carry structured
    context, not just a message" — so a caller can report *why* without a
    second round trip to the store."""

    def __init__(
        self,
        message: str,
        *,
        builder_id: str,
        reason: str,
        active_concurrent: int,
        max_concurrent: int,
        sandbox_seconds_used: float,
        sandbox_seconds_budget: float | None,
    ):
        super().__init__(message)
        self.builder_id = builder_id
        self.reason = reason  # "concurrency" or "budget"
        self.active_concurrent = active_concurrent
        self.max_concurrent = max_concurrent
        self.sandbox_seconds_used = sandbox_seconds_used
        self.sandbox_seconds_budget = sandbox_seconds_budget


# ── validation ───────────────────────────────────────────────────────────────

def _check_builder_id(builder_id: Any) -> str:
    """Delegates to principal.py's own _check_builder_id — not
    re-implemented here, see module docstring — but re-raises as
    QuotaError so every refusal this module produces is the same exception
    type regardless of which validator underneath actually caught the
    problem. Exact same shape as session.py's and checkpoint_memory.py's
    own _check_builder_id wrappers. Called before ANY file is touched by
    every public entry point below — same "no file left behind on hostile
    input" discipline the rest of this module family follows."""
    try:
        return _principal_check_builder_id(builder_id)
    except principal.PrincipalError as e:
        raise QuotaError(f"builder_id rejected: {e}") from e


def _check_positive(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QuotaError(f"{name} must be a number, got {type(value).__name__}")
    if value <= 0:
        raise QuotaError(f"{name} must be positive, got {value!r}")
    return float(value)


def _check_non_negative(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QuotaError(f"{name} must be a number, got {type(value).__name__}")
    if value < 0:
        raise QuotaError(f"{name} must not be negative, got {value!r}")
    return float(value)


def _check_max_concurrent(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise QuotaError(f"max_concurrent must be an int, got {type(value).__name__}")
    if value <= 0:
        raise QuotaError(f"max_concurrent must be positive, got {value!r}")
    return value


# ── the rows ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LeaseRecord:
    """One outstanding (or lately-outstanding) concurrency slot. Deleted on
    release rather than tombstoned — see module docstring for why that
    differs from session.py's revoked_at choice."""

    lease_id: str
    builder_id: str
    acquired_at: float
    expires_at: float

    def is_active(self, *, now: float) -> bool:
        """A half-open window, matching session.py's own expiry semantics
        (`test_a_session_still_within_its_ttl_verifies_successfully`:
        exactly-at-expiry is expired, not valid) — picked for the same
        reason: an inclusive boundary would make "expires_at == now" a
        coin flip between two call sites evaluated microseconds apart."""
        return self.expires_at > now

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "builder_id": self.builder_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LeaseRecord":
        try:
            return cls(
                lease_id=str(d["lease_id"]),
                builder_id=_check_builder_id(d["builder_id"]),
                acquired_at=float(d["acquired_at"]),
                expires_at=float(d["expires_at"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise QuotaError(f"corrupt lease row: {e}") from e


@dataclass(frozen=True)
class DurationRecord:
    """One completed build's contribution to cumulative sandbox-seconds.
    Kept as individual timestamped records (not folded into a single
    running counter) specifically so `window_seconds` can be a real filter
    — see module docstring."""

    elapsed_seconds: float
    recorded_at: float

    def to_dict(self) -> dict[str, Any]:
        return {"elapsed_seconds": self.elapsed_seconds, "recorded_at": self.recorded_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DurationRecord":
        try:
            return cls(elapsed_seconds=float(d["elapsed_seconds"]), recorded_at=float(d["recorded_at"]))
        except (KeyError, TypeError, ValueError) as e:
            raise QuotaError(f"corrupt duration record: {e}") from e


@dataclass(frozen=True)
class QuotaState:
    """A read snapshot of one builder's quota row — leases already filtered
    to `is_active(now=...)` by whoever produced this (see
    `FilesystemQuotaStore.get_state`), duration_records unfiltered (window
    filtering happens in `_sum_duration`, at the point that actually needs
    a window)."""

    builder_id: str
    leases: tuple[LeaseRecord, ...]
    duration_records: tuple[DurationRecord, ...]


@dataclass(frozen=True)
class AcquireOutcome:
    """What `QuotaStore.try_acquire_lease` decided, under its own lock.
    `lease` is populated only when `granted` is True. `active_concurrent`
    and `sandbox_seconds_used` are always populated — even on a refusal —
    so `QuotaExceededError` can carry real numbers instead of a caller
    having to re-query the store to find out what tripped the limit."""

    granted: bool
    reason: str  # "" if granted, else "concurrency" or "budget"
    active_concurrent: int
    sandbox_seconds_used: float
    lease: LeaseRecord | None


@dataclass(frozen=True)
class BuildLease:
    """Returned by `acquire_build_slot` — the caller's handle on an
    outstanding concurrency slot. Carries the store it was acquired
    against so `.release()` is a genuine convenience (`lease.release()`)
    and not just sugar that still makes the caller thread the store
    through by hand; `release_build_slot(store, lease)` is the canonical
    free-function form and is what `.release()` calls.

    The store reference is excluded from equality/repr so two leases that
    are otherwise identical compare equal regardless of which store object
    (same store, e.g. reopened) they were constructed against, and so a
    printed/logged lease never dumps a store object's own repr."""

    lease_id: str
    builder_id: str
    acquired_at: float
    expires_at: float
    _store: "QuotaStore" = field(repr=False, compare=False)

    def release(self, *, now: float | None = None) -> None:
        release_build_slot(self._store, self, now=now)


# ── storage ──────────────────────────────────────────────────────────────────

class QuotaStore(Protocol):
    """Where quota rows live. Four operations — mirroring how small
    `PrincipalStore`/`SessionStore` are kept in their own modules, for the
    same reason: a real backing store should be swappable in without a
    caller changing.

    `try_acquire_lease` carries the whole enforcement contract, the same
    way `PrincipalStore.insert_authenticator` carries its own uniqueness
    constraints rather than leaving them to a read-then-decide-then-write
    caller: it MUST evaluate the concurrency limit and (if configured) the
    sandbox-seconds budget ATOMICALLY against the current state, and MUST
    persist the new lease in the SAME atomic unit as that decision. A
    caller that reads the current count, decides in its own code, and then
    calls a separate "insert" is not implementing this Protocol, however
    much it looks like it passes on a quiet machine — that shape is
    exactly the check-then-increment race this module exists to close.

    `release_lease` MUST be idempotent: releasing an unknown or
    already-released `lease_id` is a no-op, not an error — mirroring
    `SessionStore.mark_revoked`'s own idempotency contract, so a caller's
    `finally:` block never has to track whether it already released.
    """

    def get_state(self, builder_id: str, *, now: float) -> QuotaState: ...

    def try_acquire_lease(
        self,
        *,
        builder_id: str,
        lease_id: str,
        max_concurrent: int,
        lease_ttl_seconds: float,
        sandbox_seconds_budget: float | None,
        window_seconds: float | None,
        now: float,
    ) -> AcquireOutcome: ...

    def release_lease(self, *, builder_id: str, lease_id: str, now: float) -> None: ...

    def record_duration(self, *, builder_id: str, elapsed_seconds: float, now: float) -> None: ...


def _sum_duration(
    records: tuple[DurationRecord, ...], window_seconds: float | None, now: float
) -> float:
    """The running total (`window_seconds=None`) or a real rolling-window
    sum (`window_seconds` given) over a builder's duration records — see
    module docstring's "not deferred" note. `recorded_at >= now -
    window_seconds` is a half-open window on the old end, consistent with
    `LeaseRecord.is_active`'s own half-open choice elsewhere in this
    module: a record recorded exactly `window_seconds` ago is the oldest
    one still counted."""
    if window_seconds is None:
        return sum(r.elapsed_seconds for r in records)
    cutoff = now - window_seconds
    return sum(r.elapsed_seconds for r in records if r.recorded_at >= cutoff)


class FilesystemQuotaStore:
    """DEV-ONLY reference implementation. Rows are plain JSON files under
    `root/builders/`, 0600, one file per `builder_id`, with a POSIX `flock`
    around every read and write and atomic temp-file + `os.replace()` +
    `os.fsync()` writes — the same crash-consistency discipline
    `principal.py`'s and `session.py`'s own filesystem stores use. This is
    NOT a production quota store: no backups, no replication, no
    expiry-driven cleanup of stale leases or duration history (an expired
    lease just stops counting; it does not get proactively removed from
    disk until the next successful `acquire_build_slot` for that builder
    happens to rewrite the file), and `flock` is advisory and unreliable
    over NFS. It exists so this module has something real to run and be
    tested against — including under genuine thread concurrency — before a
    real backing store lands. See the module docstring for why this
    combines file-per-builder isolation with one coarse store-wide lock
    rather than either alone.
    """

    def __init__(self, root: Path = DEFAULT_QUOTA_ROOT):
        if root.is_symlink():
            raise QuotaError(f"refusing to use a symlinked quota root: {root}")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._builders = self.root / "builders"
        self._builders.mkdir(exist_ok=True)
        os.chmod(self._builders, 0o700)
        self._lock_path = self.root / ".lock"

    # -- locking ------------------------------------------------------------

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        """One coarse lock for the whole store — see module docstring for
        why this is the deliberate choice here, same shape as
        `principal.py`'s/`session.py`'s own `_locked`. Each call opens its
        own descriptor, so this serializes threads within a process as well
        as separate processes — `flock` locks attach to the open file
        description, not the pid."""
        fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # -- paths --------------------------------------------------------------

    def _row_path(self, builder_id: str) -> Path:
        return self._builders / f"{_check_builder_id(builder_id)}.json"

    # -- io -----------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise QuotaError(f"store path exists and is not a regular file: {path}")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise QuotaError(f"store row is corrupt ({path.name}): {e}") from e

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, path)

    # -- unlocked internals (call only while holding self._locked) ----------

    def _read_state_unlocked(self, builder_id: str) -> QuotaState:
        d = self._read_json(self._row_path(builder_id))
        if d is None:
            return QuotaState(builder_id=builder_id, leases=(), duration_records=())
        try:
            leases = tuple(LeaseRecord.from_dict(row) for row in d.get("leases", []))
            duration_records = tuple(
                DurationRecord.from_dict(row) for row in d.get("duration_records", [])
            )
            stored_builder_id = str(d["builder_id"])
        except (KeyError, TypeError) as e:
            raise QuotaError(f"corrupt quota row for {builder_id!r}: {e}") from e
        if stored_builder_id != builder_id:
            raise QuotaError(
                f"store is inconsistent: builders/{builder_id}.json holds "
                f"builder_id={stored_builder_id!r}"
            )
        for lease in leases:
            if lease.builder_id != builder_id:
                raise QuotaError(
                    f"store is inconsistent: builders/{builder_id}.json holds a lease "
                    f"for builder_id={lease.builder_id!r}"
                )
        return QuotaState(builder_id=builder_id, leases=leases, duration_records=duration_records)

    def _write_state_unlocked(self, state: QuotaState) -> None:
        payload = {
            "builder_id": state.builder_id,
            "leases": [l.to_dict() for l in state.leases],
            "duration_records": [r.to_dict() for r in state.duration_records],
        }
        self._write_json(self._row_path(state.builder_id), payload)

    # -- QuotaStore Protocol --------------------------------------------------

    def get_state(self, builder_id: str, *, now: float) -> QuotaState:
        builder_id = _check_builder_id(builder_id)
        with self._locked(exclusive=False):
            state = self._read_state_unlocked(builder_id)
        active = tuple(l for l in state.leases if l.is_active(now=now))
        return QuotaState(builder_id=builder_id, leases=active, duration_records=state.duration_records)

    def try_acquire_lease(
        self,
        *,
        builder_id: str,
        lease_id: str,
        max_concurrent: int,
        lease_ttl_seconds: float,
        sandbox_seconds_budget: float | None,
        window_seconds: float | None,
        now: float,
    ) -> AcquireOutcome:
        builder_id = _check_builder_id(builder_id)
        with self._locked(exclusive=True):
            state = self._read_state_unlocked(builder_id)
            active_leases = [l for l in state.leases if l.is_active(now=now)]
            active_count = len(active_leases)
            used = _sum_duration(state.duration_records, window_seconds, now)

            if active_count >= max_concurrent:
                return AcquireOutcome(
                    granted=False, reason="concurrency", active_concurrent=active_count,
                    sandbox_seconds_used=used, lease=None,
                )
            if sandbox_seconds_budget is not None and used >= sandbox_seconds_budget:
                return AcquireOutcome(
                    granted=False, reason="budget", active_concurrent=active_count,
                    sandbox_seconds_used=used, lease=None,
                )

            lease = LeaseRecord(
                lease_id=lease_id, builder_id=builder_id, acquired_at=now,
                expires_at=now + lease_ttl_seconds,
            )
            # Persist the pruned-and-appended list — this is also where an
            # expired lease actually leaves disk (see class docstring): a
            # rejected acquire returns early without writing, so pruning
            # only lands here, on a grant.
            new_state = QuotaState(
                builder_id=builder_id, leases=tuple(active_leases) + (lease,),
                duration_records=state.duration_records,
            )
            self._write_state_unlocked(new_state)
            return AcquireOutcome(
                granted=True, reason="", active_concurrent=active_count + 1,
                sandbox_seconds_used=used, lease=lease,
            )

    def release_lease(self, *, builder_id: str, lease_id: str, now: float) -> None:
        builder_id = _check_builder_id(builder_id)
        with self._locked(exclusive=True):
            state = self._read_state_unlocked(builder_id)
            remaining = tuple(l for l in state.leases if l.lease_id != lease_id)
            if len(remaining) == len(state.leases):
                return  # idempotent: nothing to release, not an error
            new_state = QuotaState(
                builder_id=builder_id, leases=remaining, duration_records=state.duration_records
            )
            self._write_state_unlocked(new_state)

    def record_duration(self, *, builder_id: str, elapsed_seconds: float, now: float) -> None:
        builder_id = _check_builder_id(builder_id)
        with self._locked(exclusive=True):
            state = self._read_state_unlocked(builder_id)
            record = DurationRecord(elapsed_seconds=elapsed_seconds, recorded_at=now)
            new_state = QuotaState(
                builder_id=builder_id, leases=state.leases,
                duration_records=state.duration_records + (record,),
            )
            self._write_state_unlocked(new_state)

    # -- dev conveniences (not part of the Protocol) -------------------------

    def all_builder_ids(self) -> list[str]:
        with self._locked(exclusive=False):
            return sorted(p.stem for p in self._builders.glob("*.json"))


# ── the quota core ───────────────────────────────────────────────────────────

def acquire_build_slot(
    store: QuotaStore,
    builder_id: str,
    *,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT_BUILDS,
    lease_ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    sandbox_seconds_budget: float | None = None,
    window_seconds: float | None = None,
    now: float | None = None,
) -> BuildLease:
    """Claim one of this builder's `max_concurrent` concurrency slots for a
    build about to start. Fail-closed: raises `QuotaExceededError` rather
    than granting a lease when the builder is already at their concurrency
    limit (counting only non-expired leases) or — only if
    `sandbox_seconds_budget` was passed — at or over that cumulative
    sandbox-seconds budget (summed via `window_seconds`, same meaning as
    `sandbox_seconds_used`'s own parameter: `None` is the running total).

    `max_concurrent` and `lease_ttl_seconds` are per-call overrides of this
    module's own defaults (`DEFAULT_MAX_CONCURRENT_BUILDS`,
    `DEFAULT_LEASE_TTL_SECONDS`) — never a single hardcoded global limit, so
    a caller with a different fairness policy for a different builder tier
    is not blocked from expressing it.

    The caller MUST release the returned lease when the build finishes,
    success OR failure — `release_build_slot(store, lease)` or
    `lease.release()`, called from a `finally:` block the same way
    `apps/the-forge/src/the_forge/sandbox_runner.py`'s own build execution
    always cleans up regardless of outcome. This function does not, and
    cannot, do that on the caller's behalf: it has no way to know when the
    build it is leasing for has actually finished. See module docstring for
    what happens when a caller crashes before ever reaching that
    `finally:` — the lease's own TTL, not this function, is what recovers
    the slot.
    """
    builder_id = _check_builder_id(builder_id)
    max_concurrent = _check_max_concurrent(max_concurrent)
    lease_ttl_seconds = _check_positive("lease_ttl_seconds", lease_ttl_seconds)
    if sandbox_seconds_budget is not None:
        sandbox_seconds_budget = _check_non_negative("sandbox_seconds_budget", sandbox_seconds_budget)
    if window_seconds is not None:
        window_seconds = _check_positive("window_seconds", window_seconds)

    now = time.time() if now is None else now
    lease_id = secrets.token_hex(_LEASE_ID_BYTES)

    outcome = store.try_acquire_lease(
        builder_id=builder_id, lease_id=lease_id, max_concurrent=max_concurrent,
        lease_ttl_seconds=lease_ttl_seconds, sandbox_seconds_budget=sandbox_seconds_budget,
        window_seconds=window_seconds, now=now,
    )

    if not outcome.granted:
        if outcome.reason == "concurrency":
            message = (
                f"builder_id={builder_id!r} is already at its concurrency limit "
                f"({outcome.active_concurrent}/{max_concurrent} builds running) — refusing "
                f"to start another until one finishes or a lease's TTL elapses"
            )
        else:
            message = (
                f"builder_id={builder_id!r} is over its sandbox-seconds budget "
                f"({outcome.sandbox_seconds_used:.1f}s used, budget {sandbox_seconds_budget:.1f}s) — "
                f"refusing to start another build"
            )
        raise QuotaExceededError(
            message, builder_id=builder_id, reason=outcome.reason,
            active_concurrent=outcome.active_concurrent, max_concurrent=max_concurrent,
            sandbox_seconds_used=outcome.sandbox_seconds_used,
            sandbox_seconds_budget=sandbox_seconds_budget,
        )

    lease = outcome.lease
    assert lease is not None  # granted implies a lease — the Protocol's own contract
    return BuildLease(
        lease_id=lease.lease_id, builder_id=lease.builder_id,
        acquired_at=lease.acquired_at, expires_at=lease.expires_at, _store=store,
    )


def release_build_slot(store: QuotaStore, lease: BuildLease, *, now: float | None = None) -> None:
    """Free the concurrency slot `lease` holds. Idempotent and silent on an
    already-released or unknown lease — see `QuotaStore.release_lease`'s
    contract — so this is always safe to call from a `finally:` block
    without a caller having to track whether it already released, the same
    "don't make idempotency the caller's problem" posture
    `session.py`'s `revoke_session` already follows for its own writes."""
    now = time.time() if now is None else now
    store.release_lease(builder_id=lease.builder_id, lease_id=lease.lease_id, now=now)


def record_build_duration(
    store: QuotaStore, builder_id: str, elapsed_seconds: float, *, now: float | None = None
) -> None:
    """Record that `builder_id` just consumed `elapsed_seconds` of sandboxed
    execution time — the integration point for
    `apps/the-forge/src/the_forge/sandbox_runner.py`'s own
    `SandboxRun.elapsed_s`, though wiring that call site is explicitly not
    this module's job (see module docstring). Call this once per completed
    build, independent of whether that build also held a lease that has
    already been released — the two are tracked separately (concurrency vs.
    cumulative time) and neither implies the other happened."""
    builder_id = _check_builder_id(builder_id)
    elapsed_seconds = _check_non_negative("elapsed_seconds", elapsed_seconds)
    now = time.time() if now is None else now
    store.record_duration(builder_id=builder_id, elapsed_seconds=elapsed_seconds, now=now)


def sandbox_seconds_used(
    store: QuotaStore, builder_id: str, *, window_seconds: float | None = None,
    now: float | None = None,
) -> float:
    """This builder's cumulative sandboxed execution time — the running
    total (`window_seconds=None`, the default) or a real rolling-window sum
    over the last `window_seconds` (see module docstring for why this is
    not a deferred/placeholder feature)."""
    builder_id = _check_builder_id(builder_id)
    if window_seconds is not None:
        window_seconds = _check_positive("window_seconds", window_seconds)
    now = time.time() if now is None else now
    state = store.get_state(builder_id, now=now)
    return _sum_duration(state.duration_records, window_seconds, now)


def active_build_count(store: QuotaStore, builder_id: str, *, now: float | None = None) -> int:
    """How many of this builder's leases are non-expired right now — a
    read-only convenience over `QuotaStore.get_state`, not part of the
    enforcement path itself (enforcement happens inside
    `try_acquire_lease`, under lock; this is for a caller or test that just
    wants to look)."""
    builder_id = _check_builder_id(builder_id)
    now = time.time() if now is None else now
    state = store.get_state(builder_id, now=now)
    return len(state.leases)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _store(args: argparse.Namespace) -> FilesystemQuotaStore:
    return FilesystemQuotaStore(Path(args.root))


def _cmd_acquire(args: argparse.Namespace) -> int:
    try:
        lease = acquire_build_slot(
            _store(args), args.builder_id, max_concurrent=args.max_concurrent,
            lease_ttl_seconds=args.lease_ttl_seconds,
            sandbox_seconds_budget=args.sandbox_seconds_budget,
        )
    except QuotaError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({
        "lease_id": lease.lease_id, "builder_id": lease.builder_id,
        "acquired_at": lease.acquired_at, "expires_at": lease.expires_at,
    }, indent=2, sort_keys=True))
    return 0


def _cmd_release(args: argparse.Namespace) -> int:
    store = _store(args)
    lease = BuildLease(
        lease_id=args.lease_id, builder_id=args.builder_id,
        acquired_at=0.0, expires_at=0.0, _store=store,
    )
    try:
        release_build_slot(store, lease)
    except QuotaError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print("released")
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    try:
        record_build_duration(_store(args), args.builder_id, args.elapsed_seconds)
    except QuotaError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print("recorded")
    return 0


def _cmd_used(args: argparse.Namespace) -> int:
    try:
        used = sandbox_seconds_used(_store(args), args.builder_id, window_seconds=args.window_seconds)
    except QuotaError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"sandbox_seconds_used": used}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quota.py")
    p.add_argument("--root", default=str(DEFAULT_QUOTA_ROOT))
    sub = p.add_subparsers(dest="command", required=True)

    ac = sub.add_parser("acquire", help="claim a concurrency slot for a build about to start")
    ac.add_argument("builder_id")
    ac.add_argument("--max-concurrent", type=int, default=DEFAULT_MAX_CONCURRENT_BUILDS)
    ac.add_argument("--lease-ttl-seconds", type=float, default=DEFAULT_LEASE_TTL_SECONDS)
    ac.add_argument("--sandbox-seconds-budget", type=float, default=None)
    ac.set_defaults(func=_cmd_acquire)

    rl = sub.add_parser("release", help="free a concurrency slot")
    rl.add_argument("builder_id")
    rl.add_argument("lease_id")
    rl.set_defaults(func=_cmd_release)

    rc = sub.add_parser("record", help="record a completed build's sandboxed duration")
    rc.add_argument("builder_id")
    rc.add_argument("elapsed_seconds", type=float)
    rc.set_defaults(func=_cmd_record)

    us = sub.add_parser("used", help="cumulative sandbox-seconds for a builder")
    us.add_argument("builder_id")
    us.add_argument("--window-seconds", type=float, default=None)
    us.set_defaults(func=_cmd_used)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
