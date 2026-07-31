#!/usr/bin/env python3
"""stores/session.py — store-native session tokens (D11, docs/design/the-forge.md).

D11 says: "safe-app-store issues its own session tokens after a GitHub OAuth
handshake completes. No password storage, no reset flow to build." This
module is that layer, and nothing more. `stores/principal.py` already mints
the store-owned `builder_id` and binds an external authenticator to it; this
module assumes that has already happened (the caller hands it a `builder_id`
principal.py already resolved) and answers a narrower question: "given a
verified `builder_id`, hand back something a browser can carry on every
later request, and let the store check that thing without re-running OAuth."

Store-side authority (D1), same trust level and same directory as
`principal.py` and `sap_gate.py`, for the same reason both of those name:
`apps/the-forge/` never imports this — the host imports the builder, never
the reverse, and the same direction holds for who gets to say a session is
still good. A build in `apps/` has no business minting or verifying its own
sessions; that stays store-side.

**Bearer token, not a JWT.** A session token here is 256 bits from
`secrets.token_urlsafe(32)` — the same `secrets` module `principal.py` uses
for `builder_id`, no home-rolled randomness. It carries no encoded claims:
unlike a JWT, a leaked or logged token reveals nothing about `builder_id`,
`issued_at`, or anything else — the only way to learn what it's good for is
to ask the store, which is also the only place that can revoke it. That
opacity is deliberate, not a missing feature: a self-describing token can't
be revoked before its own expiry without an allow/deny-list anyway, so there
is no capability lost by making the store the sole source of truth.

**Only a hash of the token is ever persisted — never the raw token.**
Mirrors `principal.py`'s reasoning for its digest-named authenticator files
exactly: a directory listing, a backup, or a compromised filesystem must not
hand out live, usable sessions. `hashlib.sha256(token)` is both the lookup
key and (per `principal.py`'s own `_auth_path` shape) the filename — a
filesystem compromise gets a list of hashes it cannot turn back into
bearer-usable tokens (256 bits of entropy makes the hash useless to search
against, unlike principal.py's `(provider, external_id)` hash, which is only
trying to hide a pair that's small and guessable — here the hash is hiding a
secret that's already unguessable, so this buys defense in depth against a
disk compromise, not confidentiality on its own).

**Revocation is a field on the row, not a second file.** `principal.py`'s
own 2026-08-01 fix note describes exactly the bug class a second file
invites: two writes under one lock close the race between concurrent
CALLERS, but not a crash between the two writes, and picking which of two
files should exist after a crash is exactly the kind of judgment call that
bug required. A session row lives at exactly one path
(`sessions/<sha256(token)>.json`), keyed by the token hash, holding a
`revoked_at: float | None` field that starts `None` and is set once. One
file means one atomic replace makes every state transition (mint, revoke)
crash-consistent by construction — there is no second index to get out of
order with the first, so that whole bug class does not apply here. A
tombstone (delete-on-revoke) was the other option considered: rejected
because a missing row and a revoked row would then look identical to
`verify_session`, `revoke_session` couldn't be idempotent (a second revoke
of an already-tombstoned session has nothing to update), and there would be
no record left to explain *why* a bearer got refused — a `revoked_at`
timestamp is strictly more information for roughly the same cost.

**Verify, don't leak which way a token failed.** An unknown token hash, an
expired session, and a revoked session all return `None` from
`verify_session` — the same value, the same code path shape, no distinct
exception type a caller could pattern-match on to learn which case
happened. This matters because "unknown" vs "expired" vs "revoked" is
itself information an attacker probing tokens could use (an "expired"
answer confirms the token was once real). The lookup is by hash, not by
scanning and comparing candidate tokens, so there is no per-guess timing
signal to begin with — a wrong token hashes to a path that does not exist,
which is indistinguishable on disk from a right-token-but-expired row that
does exist. Both paths return `None`; neither raises.

Not in scope, deliberately — the boundary this module stops at:
  * The GitHub OAuth handshake itself (redirect, `state`/PKCE, code-for-token
    exchange, callback route) — `principal.py`'s own docstring already
    states this boundary and it holds here too; this module starts *after*
    a `builder_id` already exists.
  * Deciding whether a `builder_id` is even allowed to have a session
    (suspension, banning, quota) — a session-issuance policy question, not
    a session-mechanics one; `mint_session` trusts its caller's decision to
    call it, the same way `principal.py`'s `bind_authenticator` trusts its
    caller that verification already happened.
  * Re-linking a second authenticator to a `builder_id` — `principal.py`'s
    own docstring names this as a real, still-open D11 v1 gap; nothing
    here closes it, and nothing here needed to.

Usage:
    python stores/session.py mint <builder_id> [--ttl-seconds N]
    python stores/session.py verify <token>
    python stores/session.py revoke <token>
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import secrets
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

DEFAULT_SESSION_ROOT = Path(__file__).resolve().parent / ".sessions"

# One day. A dev-reasonable default, not a claim about what production
# should use — a real deployment's session lifetime is a product decision
# (D11's Open/next names GitHub App registration specifics, callback/session
# lifetime among them, as still open) and callers are free to pass their own
# `ttl_seconds` to `mint_session`.
DEFAULT_TTL_SECONDS = 24 * 60 * 60

# 256 bits — deliberately larger than principal.py's 128-bit builder_id.
# builder_id only has to resist being *guessed among all minted ids*; a
# session token additionally has to resist being *guessed cold*, with no
# rate limit assumed at this layer, by anyone who intercepts none of the
# traffic that would carry it. secrets.token_urlsafe's default recommendation
# for exactly this use (an unguessable bearer credential) is what's used
# here, not a smaller value chosen to "match" builder_id.
_TOKEN_BYTES = 32

# principal.py is loaded the same way stores/seam.py loads stores/sap_gate.py
# — spec_from_file_location, not a package-relative import, because stores/
# has no __init__.py and is run as a directory of standalone scripts, not
# installed as a package. `_check_builder_id` is imported directly rather
# than re-implemented: principal.py is the one place a builder_id's
# path-safety charset is defined, and re-deriving that rule here would be
# exactly the kind of drift D11's own docstring warns against (a second,
# possibly-diverging copy of a security-relevant check).
_REPO = Path(__file__).resolve().parent.parent
_principal_spec = importlib.util.spec_from_file_location(
    "principal", Path(__file__).resolve().parent / "principal.py"
)
principal = importlib.util.module_from_spec(_principal_spec)
sys.modules["principal"] = principal
_principal_spec.loader.exec_module(principal)

_principal_check_builder_id = principal._check_builder_id


class SessionError(Exception):
    """Fail-closed refusal — bad builder_id, a store that did not honor its
    own contract, or an inconsistent store. Every refusal in this module
    raises; `verify_session` is the one deliberate exception, returning
    `None` for "not currently valid" because that is an answer, not a
    failure (see module docstring, "verify, don't leak")."""


def _check_token(token: Any) -> str:
    if not isinstance(token, str):
        raise SessionError(f"token must be a str, got {type(token).__name__}")
    if not token:
        raise SessionError("token must not be empty")
    return token


def _check_builder_id(builder_id: Any) -> str:
    """Delegates the actual charset/type check to `principal.py`'s own
    `_check_builder_id` — not re-implemented here, see module docstring —
    but re-raises as `SessionError` so every refusal this module produces
    is the same exception type regardless of which validator underneath
    actually caught the problem. A caller of session.py should never need
    to import principal.py just to catch its exception type."""
    try:
        return _principal_check_builder_id(builder_id)
    except principal.PrincipalError as e:
        raise SessionError(f"builder_id rejected: {e}") from e


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── the row ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionRecord:
    """The on-disk row for one session. Deliberately holds no raw token —
    see the module docstring's "only a hash is ever persisted" section.
    `token_hash` is stored inside the row itself, not just implied by the
    filename it lives at, for the same reason `principal.py`'s
    `Authenticator.key()` is re-checked against the filename it was fetched
    from: a digest filename means "a file exists here" is not the same fact
    as "this row is the one that was asked for," and that has to be checked,
    not assumed."""

    token_hash: str
    builder_id: str
    issued_at: float
    expires_at: float
    revoked_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_hash": self.token_hash,
            "builder_id": self.builder_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionRecord":
        try:
            revoked_at = d["revoked_at"]
            return cls(
                token_hash=str(d["token_hash"]),
                builder_id=_check_builder_id(d["builder_id"]),
                issued_at=float(d["issued_at"]),
                expires_at=float(d["expires_at"]),
                revoked_at=None if revoked_at is None else float(revoked_at),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise SessionError(f"corrupt session row: {e}") from e


@dataclass(frozen=True)
class Session:
    """Returned by `mint_session` ONLY — the one and only place the raw
    token is visible after generation. Nothing this module persists ever
    holds `token`; every other function that touches a session (`verify_session`,
    `revoke_session`) takes the raw token in and gives back a `builder_id` or
    nothing, never a `Session` reconstructed from disk."""

    token: str
    builder_id: str
    issued_at: float
    expires_at: float

    def to_public_dict(self) -> dict[str, Any]:
        """For the CLI / a caller that wants to hand the token to a browser
        — named `_public` because, unlike `SessionRecord.to_dict`, this DOES
        carry the raw token; it must never be what gets written to disk."""
        return {
            "token": self.token,
            "builder_id": self.builder_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


# ── storage ──────────────────────────────────────────────────────────────────

class SessionStore(Protocol):
    """Where session rows live. Three operations, on purpose — mirroring
    how small `PrincipalStore` is kept in `principal.py`, for the same
    reason: a real backing store (Redis with a TTL, a SQL table, whatever
    D6's tenancy work lands on) should be swappable in without a caller
    changing.

    `insert_session` MUST NOT silently overwrite an existing row at the
    same `token_hash` — a collision at 256 bits of entropy is not something
    that should ever legitimately happen, and treating it as an overwrite
    would mean a vanishingly-unlikely accident could invalidate someone
    else's live session rather than being caught as the anomaly it is.

    `mark_revoked` MUST be idempotent: revoking an unknown `token_hash`, or
    one that is already revoked, is a no-op rather than an error — the same
    "don't leak which case it was" posture `verify_session` follows (see
    module docstring), applied to the write side, and it is what makes
    `revoke_session` safe to call twice without a caller having to track
    whether it already did.
    """

    def get_session(self, token_hash: str) -> SessionRecord | None: ...

    def insert_session(self, record: SessionRecord) -> None: ...

    def mark_revoked(self, token_hash: str, *, revoked_at: float) -> None: ...


class FilesystemSessionStore:
    """DEV-ONLY reference implementation. Rows are plain JSON files under
    `root/sessions/`, 0600, one file per session keyed by
    `sha256(token)`, with a POSIX `flock` around every read and write and
    atomic temp-file + `os.replace()` + `os.fsync()` writes — the same
    crash-consistency discipline `principal.py`'s `FilesystemPrincipalStore`
    uses. This is NOT a production session store: no backups, no
    replication, no expiry-driven cleanup (an expired row just sits on disk
    until something reaps it), and `flock` is advisory and unreliable over
    NFS. It exists so this module has something real to run and be tested
    against — including under genuine thread and process concurrency —
    before a real backing store (one with a native TTL, ideally) lands.

    One file per session, deliberately, rather than `principal.py`'s
    two-index layout: `principal.py` needs a forward AND a reverse index
    because it enforces two independent uniqueness constraints
    ((provider, external_id) -> builder_id, and builder_id -> at most one
    authenticator). A session has exactly one natural key — the token hash
    — and nothing here needs a reverse lookup by `builder_id` (revocation
    and verification both arrive already holding the raw token), so there
    is no second file to keep in order with the first, and the crash-between-
    two-writes bug class `principal.py`'s 2026-08-01 fix note describes does
    not have anywhere to occur.
    """

    def __init__(self, root: Path = DEFAULT_SESSION_ROOT):
        if root.is_symlink():
            raise SessionError(f"refusing to use a symlinked session root: {root}")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._sessions = self.root / "sessions"
        self._sessions.mkdir(exist_ok=True)
        os.chmod(self._sessions, 0o700)
        self._lock_path = self.root / ".lock"

    # -- locking ------------------------------------------------------------

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        """One coarse lock for the whole store, same shape and same
        reasoning as `principal.py`'s `_locked`: a directory of files has
        no transaction to lean on, and a lock that is obviously correct
        beats a clever per-row scheme that is subtly not. Each call opens
        its own descriptor, so this serializes threads within a process as
        well as separate processes — `flock` locks attach to the open file
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

    def _session_path(self, token_hash: str) -> Path:
        return self._sessions / f"{token_hash}.json"

    # -- io -----------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise SessionError(f"store path exists and is not a regular file: {path}")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise SessionError(f"store row is corrupt ({path.name}): {e}") from e

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

    # -- reads --------------------------------------------------------------

    def get_session(self, token_hash: str) -> SessionRecord | None:
        with self._locked(exclusive=False):
            return self._get_session_unlocked(token_hash)

    def _get_session_unlocked(self, token_hash: str) -> SessionRecord | None:
        d = self._read_json(self._session_path(token_hash))
        if d is None:
            return None
        record = SessionRecord.from_dict(d)
        if record.token_hash != token_hash:
            # Same check principal.py's _get_authenticator_unlocked makes on
            # its digest-named files: the filename matching is not proof the
            # row inside is the one that was asked for.
            raise SessionError(
                f"store is inconsistent: sessions/{token_hash}.json holds "
                f"token_hash={record.token_hash!r}"
            )
        return record

    # -- writes ---------------------------------------------------------------

    def insert_session(self, record: SessionRecord) -> None:
        with self._locked(exclusive=True):
            path = self._session_path(record.token_hash)
            if path.exists():
                # 256 bits of entropy makes this a collision, a corrupted
                # store, or a bug — never a legitimate re-mint. Fail closed
                # rather than silently overwriting a row that might still be
                # a live session for someone else.
                raise SessionError(
                    f"refusing to overwrite an existing session row at "
                    f"token_hash={record.token_hash!r}"
                )
            self._write_json(path, record.to_dict())

    def mark_revoked(self, token_hash: str, *, revoked_at: float) -> None:
        with self._locked(exclusive=True):
            existing = self._get_session_unlocked(token_hash)
            if existing is None:
                return  # idempotent: nothing to revoke, not an error
            if existing.revoked_at is not None:
                return  # idempotent: already revoked, first timestamp stands
            updated = SessionRecord(
                token_hash=existing.token_hash,
                builder_id=existing.builder_id,
                issued_at=existing.issued_at,
                expires_at=existing.expires_at,
                revoked_at=revoked_at,
            )
            self._write_json(self._session_path(token_hash), updated.to_dict())

    # -- dev conveniences (not part of the Protocol) ------------------------

    def all_token_hashes(self) -> list[str]:
        with self._locked(exclusive=False):
            return sorted(p.stem for p in self._sessions.glob("*.json"))


# ── the session core ────────────────────────────────────────────────────────

def mint_session(
    store: SessionStore, builder_id: str, *, ttl_seconds: float = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> Session:
    """Issue a new session for an already-verified `builder_id`.

    `builder_id` is validated with `principal.py`'s own `_check_builder_id`
    — not re-implemented here — so a caller cannot mint a session for
    something that could never have been a real minted identity (a
    traversal string, an empty string, anything that fails the same
    path-safety charset D6/D11 require everywhere else). This function does
    NOT check that `builder_id` was actually minted by a real
    `PrincipalStore` — it only knows the shape is legal, the same boundary
    `principal.py`'s `bind_authenticator` draws around its own caller: the
    caller (the OAuth callback handler, once it exists) is responsible for
    only calling this with a `builder_id` `resolve_verified_identity` just
    returned.

    The raw token is generated here, handed back on the returned `Session`,
    and never touches the store — `store.insert_session` only ever receives
    a `SessionRecord`, which does not have a `token` field to leak.
    """
    builder_id = _check_builder_id(builder_id)
    if ttl_seconds <= 0:
        raise SessionError(f"ttl_seconds must be positive, got {ttl_seconds!r}")

    issued_at = time.time() if now is None else now
    expires_at = issued_at + ttl_seconds
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    record = SessionRecord(
        token_hash=_token_hash(token),
        builder_id=builder_id,
        issued_at=issued_at,
        expires_at=expires_at,
        revoked_at=None,
    )
    store.insert_session(record)
    return Session(token=token, builder_id=builder_id, issued_at=issued_at, expires_at=expires_at)


def verify_session(store: SessionStore, token: str, *, now: float | None = None) -> str | None:
    """The `builder_id` for a valid, unexpired, unrevoked session token —
    `None` for anything else.

    "Anything else" is deliberately one bucket, not three: an unrecognized
    token, an expired session whose row is still on disk, and a revoked
    session all return `None` through the exact same return statement, with
    no distinguishing exception type or code path a caller could inspect
    (see module docstring, "verify, don't leak"). Expiry is checked against
    `now` — real wall-clock time by default, injectable for tests, matching
    `principal.py`'s own `now: float | None = None` convention rather than
    inventing a new one.
    """
    token = _check_token(token)
    now = time.time() if now is None else now

    record = store.get_session(_token_hash(token))
    if record is None:
        return None
    if record.revoked_at is not None:
        return None
    if record.expires_at <= now:
        return None
    return record.builder_id


def revoke_session(store: SessionStore, token: str, *, now: float | None = None) -> None:
    """Make a previously-valid token verify to `None` immediately
    afterward. Idempotent and silent on an unknown or already-revoked
    token — see `SessionStore.mark_revoked`'s contract — for the same
    "don't leak which case it was" reason `verify_session` collapses its
    own three failure cases into one."""
    token = _check_token(token)
    now = time.time() if now is None else now
    store.mark_revoked(_token_hash(token), revoked_at=now)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _store(args: argparse.Namespace) -> FilesystemSessionStore:
    return FilesystemSessionStore(Path(args.root))


def _cmd_mint(args: argparse.Namespace) -> int:
    try:
        session = mint_session(_store(args), args.builder_id, ttl_seconds=args.ttl_seconds)
    except SessionError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps(session.to_public_dict(), indent=2, sort_keys=True))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        builder_id = verify_session(_store(args), args.token)
    except SessionError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if builder_id is None:
        print("(invalid, expired, or revoked)")
        return 1
    print(builder_id)
    return 0


def _cmd_revoke(args: argparse.Namespace) -> int:
    try:
        revoke_session(_store(args), args.token)
    except SessionError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print("revoked")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="session.py")
    p.add_argument("--root", default=str(DEFAULT_SESSION_ROOT))
    sub = p.add_subparsers(dest="command", required=True)

    mn = sub.add_parser("mint", help="issue a new session token for a builder_id")
    mn.add_argument("builder_id")
    mn.add_argument("--ttl-seconds", type=float, default=DEFAULT_TTL_SECONDS)
    mn.set_defaults(func=_cmd_mint)

    vf = sub.add_parser("verify", help="builder_id for a valid session token, or a refusal")
    vf.add_argument("token")
    vf.set_defaults(func=_cmd_verify)

    rv = sub.add_parser("revoke", help="revoke a session token")
    rv.add_argument("token")
    rv.set_defaults(func=_cmd_revoke)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
