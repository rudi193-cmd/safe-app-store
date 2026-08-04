#!/usr/bin/env python3
"""stores/principal.py — store-minted identity (D11, docs/design/the-forge.md).

The store owns its own identity namespace. That is the whole point of this
module, and it is store-side authority (D1) for the same reason
`stores/sap_gate.py` is: `apps/the-forge/` never imports this: the host
imports the builder, never the reverse, and the same direction holds for who
gets to say who someone *is*.

D11's fix, restated as code: an earlier draft derived `builder_id` straight
from GitHub's stable user ID, which quietly made GitHub the root of the
store's identity namespace — exactly what D1 rules out. Here, a `builder_id`
is **minted by this module** from `secrets.token_hex` and is not derived
from, does not contain, and cannot be reconstructed from anything an external
provider returns. GitHub is recorded as one **authenticator** row —
`{provider, external_id, linked_at}` bound to that minted id — which makes it
what D1 says every external system is: a capability provider ("this session
belongs to GitHub account X"), never an authority. A renamed, deleted, or
re-used GitHub account moves exactly one row and nothing else; every
downstream system (D4's keyring, D6's `apps/<builder_id>/`, D9/D12's Nestor
domain, D1/D5's Casbin `caller`) keys off the minted id and never sees the
external one.

Uniqueness is the mechanism, so it is enforced rather than assumed. Two
constraints, both real, both checked by the store inside one atomic unit:

  1. `(provider, external_id)` -> at most one `builder_id`, forever. Without
     this the D11 fix is cosmetic — anything that could claim an
     `external_id` at bind time would still be claiming someone else's
     identity, just one indirection later.
  2. `builder_id` -> at most one authenticator (D11 v1: minted once, one
     authenticator, no re-linking flow yet). This is also the
     account-takeover guard: "bind my GitHub account to *your* builder_id"
     is refused, not merely unlikely.

Neither is a check-then-write. `PrincipalStore.insert_authenticator` is
specified as an atomic insert that returns the existing conflicting row
rather than overwriting it — the same shape a SQL table with two UNIQUE
indexes and one INSERT would have. Callers here never read-then-decide; they
insert and read the outcome. See `resolve_verified_identity` for how that
kills the concurrent-first-login race outright instead of compensating for
it afterwards.

Charset: `builder_id` becomes a filesystem path component (D6:
`apps/<builder_id>/<app_name>/`) and a collection-namespace component
(`saps1/builder-<builder_id>/`), so it carries the same rule this repo
already enforces in `stores/sap_gate.py` (`_BUILDER_ID_PATTERN`) and
`the_forge/plan.py` (`_APP_NAME_PATTERN`). `provider` and `external_id` get
the identical rule even though the dev store hashes them before they ever
reach a filename — the 2026-08-01 audit's rule is that any identifier that
*could* land in a path is validated, and a future backing store that keys
rows by the raw pair should not be the thing that discovers this module
never checked.

Custody note, in the same spirit as sap_gate's: `FilesystemPrincipalStore`
is a DEV-ONLY reference implementation. It is real (POSIX `flock`, atomic
replace, both uniqueness constraints genuinely enforced across threads and
processes on a local filesystem) and it is NOT a production identity store —
no backups, no replication, an O(1)-but-unindexed directory per row, and
`flock` semantics that are advisory and unreliable over NFS. It exists so
this module has something honest to run and be tested against before a real
backing store lands, and it says so rather than pretending.

Not in scope, deliberately — the boundary this module stops at:
  * The GitHub OAuth handshake itself: authorization redirect, `state`/PKCE,
    the code-for-token exchange, the callback route. Everything here starts
    *after* that succeeded and consumes its result as a `(provider,
    external_id)` pair. See `resolve_verified_identity`.
  * Session tokens and their lifetime — D11 says the store issues its own;
    what they look like and how long they live is a live question in the
    design doc's Open/next, not something to guess at here.
  * The GitHub App registration and its requested scopes (also Open/next:
    whether this org reuses an existing registration or needs its own).
  * Re-linking / second-authenticator flows — D11 v1 says one, permanently,
    and names that a real gap. Constraint 2 above is that gap, enforced.
  * A binding-event ledger. D10 defines three audit trails and this is not
    one of them; adding a fourth is a design decision, not something to do
    silently inside an identity module.

Usage:
    python stores/principal.py login --provider github --external-id 4242
    python stores/principal.py lookup --provider github --external-id 4242
    python stores/principal.py show <builder_id>
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

DEFAULT_PRINCIPAL_ROOT = Path(__file__).resolve().parent / ".principals"

# Same charset rule, from the same place, for the same reason: these become
# filesystem path components. sap_gate.py's _BUILDER_ID_PATTERN and
# the_forge/plan.py's _APP_NAME_PATTERN are the existing instances; this is
# the third, not a fourth rule invented here.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_MAX_BUILDER_ID_LEN = 128
_MAX_EXTERNAL_ID_LEN = 255
_MAX_PROVIDER_LEN = 32

# 128 bits. Not a namespace, not a checksum, not a prefix that encodes where
# the identity came from — an opaque token nothing downstream should parse.
_BUILDER_ID_BYTES = 16

# Default-deny, same posture as D5's per-server tool allowlist: a provider
# name is not a free-form string a caller gets to invent. Two providers that
# are really the same account source ("github", "github.com", "gh") would
# mint two builder_ids for one human and split their identity in half —
# adding one here is a deliberate edit, made once, with that in mind.
KNOWN_PROVIDERS = frozenset({"github"})


class PrincipalError(Exception):
    """Fail-closed refusal — bad charset, unknown provider, a store that did
    not honor its own contract, or an inconsistent store. Every refusal in
    this module raises; nothing returns a bool a caller could forget to
    check. The one deliberate exception is `lookup_builder_id`, which
    returns None for "never seen" because that is an answer, not a failure."""


class AuthenticatorConflict(PrincipalError):
    """A bind was refused because it would have violated one of the two
    uniqueness constraints. Carries the row that actually holds the ground,
    so a caller can tell "already yours" from "already someone else's"
    without re-reading the store."""

    def __init__(self, message: str, *, existing: "Authenticator"):
        super().__init__(message)
        self.existing = existing


# ── validation ───────────────────────────────────────────────────────────────

def _check_builder_id(builder_id: Any) -> str:
    if not isinstance(builder_id, str):
        raise PrincipalError(f"builder_id must be a str, got {type(builder_id).__name__}")
    if not builder_id or not _ID_PATTERN.match(builder_id):
        raise PrincipalError(f"builder_id {builder_id!r} fails the path-safety charset (D11)")
    if len(builder_id) > _MAX_BUILDER_ID_LEN:
        raise PrincipalError(f"builder_id is longer than {_MAX_BUILDER_ID_LEN} characters")
    return builder_id


def _check_provider(provider: Any) -> str:
    """Normalizes case *before* the allowlist check, on purpose. "GitHub"
    and "github" are the same account source; letting both through as
    distinct keys would give one human two builder_ids depending on how the
    callback happened to spell it — a split-identity bug that looks like
    nothing until someone's apps vanish."""
    if not isinstance(provider, str):
        raise PrincipalError(f"provider must be a str, got {type(provider).__name__}")
    if len(provider) > _MAX_PROVIDER_LEN:
        raise PrincipalError(f"provider is longer than {_MAX_PROVIDER_LEN} characters")
    normalized = provider.lower()
    if not normalized or not _ID_PATTERN.match(normalized):
        raise PrincipalError(f"provider {provider!r} fails the path-safety charset")
    if normalized not in KNOWN_PROVIDERS:
        raise PrincipalError(
            f"provider {normalized!r} is not registered — known providers: "
            f"{sorted(KNOWN_PROVIDERS)} (default-deny, see KNOWN_PROVIDERS)"
        )
    return normalized


def _check_external_id(external_id: Any) -> str:
    """Strings only, and deliberately not coerced. GitHub's `/user` returns
    `id` as a JSON number; a caller that passes the int here and the str
    there would key one account two different ways and mint it two
    identities. Refusing makes the caller stringify once, at the OAuth
    boundary, where the decision is visible.

    No case normalization, unlike `provider`: `external_id` is an opaque
    identifier belonging to someone else's namespace, and folding case could
    merge two genuinely distinct accounts in a provider whose ids are
    case-sensitive."""
    if not isinstance(external_id, str):
        raise PrincipalError(
            f"external_id must be a str, got {type(external_id).__name__} — "
            f"stringify it at the OAuth boundary rather than relying on coercion here"
        )
    if not external_id or not _ID_PATTERN.match(external_id):
        raise PrincipalError(f"external_id {external_id!r} fails the path-safety charset")
    if len(external_id) > _MAX_EXTERNAL_ID_LEN:
        raise PrincipalError(f"external_id is longer than {_MAX_EXTERNAL_ID_LEN} characters")
    return external_id


# ── the two rows ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """A store-owned identity. Deliberately holds nothing an external
    provider told us — no login name, no email, no avatar. The store needs
    to know that this builder exists and when it started existing; mirroring
    a GitHub profile into it would re-import the coupling D11 just removed
    (and would make a rename someone else's problem to propagate)."""

    builder_id: str
    minted_at: float

    def to_dict(self) -> dict[str, Any]:
        return {"builder_id": self.builder_id, "minted_at": self.minted_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Principal":
        try:
            return cls(builder_id=_check_builder_id(d["builder_id"]), minted_at=float(d["minted_at"]))
        except (KeyError, TypeError, ValueError) as e:
            raise PrincipalError(f"corrupt principal row: {e}") from e


@dataclass(frozen=True)
class Authenticator:
    """One external identity, bound to one store-minted `builder_id`. This
    row *is* D11's fix: GitHub appears here and nowhere else in the
    identity graph."""

    provider: str
    external_id: str
    builder_id: str
    linked_at: float

    def key(self) -> tuple[str, str]:
        return (self.provider, self.external_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "external_id": self.external_id,
            "builder_id": self.builder_id,
            "linked_at": self.linked_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Authenticator":
        try:
            return cls(
                provider=_check_provider(d["provider"]),
                external_id=_check_external_id(d["external_id"]),
                builder_id=_check_builder_id(d["builder_id"]),
                linked_at=float(d["linked_at"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise PrincipalError(f"corrupt authenticator row: {e}") from e


@dataclass(frozen=True)
class LoginResult:
    """`created` distinguishes "this account has never been here before"
    from "welcome back" — the two are the same call on purpose (see
    `resolve_verified_identity`), but a caller provisioning D6's
    `apps/<builder_id>/` or D4's keyring needs to know which one happened."""

    builder_id: str
    created: bool
    authenticator: Authenticator


# ── storage ──────────────────────────────────────────────────────────────────

class PrincipalStore(Protocol):
    """Where identity rows live. Small on purpose: three reads and one
    write, so a real backing store (Postgres, SQLite, whatever D6's tenancy
    work lands on) can be swapped in without a caller changing.

    The write carries the whole contract, and it is the reason the race in
    `resolve_verified_identity` is closed rather than narrowed:

    `insert_authenticator(auth, new_principal=...)` MUST be atomic against
    concurrent callers, MUST enforce both uniqueness constraints
    (`(provider, external_id)` unique, and `builder_id` unique across
    authenticators), MUST NOT modify anything when either constraint would
    be violated, and MUST return the existing row that blocked the insert so
    the caller can tell what happened. When `new_principal` is given, the
    principal row is created in the SAME atomic unit as the authenticator
    row — that is what makes an orphaned, unreachable principal from a lost
    race structurally impossible rather than something to clean up
    afterwards.

    In SQL that is one INSERT into a table with two UNIQUE indexes, inside
    one transaction with the principals INSERT. Any implementation that
    reads, decides, then writes is not implementing this Protocol, however
    much it looks like it passes on a quiet machine.
    """

    def get_principal(self, builder_id: str) -> Principal | None: ...

    def get_authenticator(self, provider: str, external_id: str) -> Authenticator | None: ...

    def get_authenticator_for_builder(self, builder_id: str) -> Authenticator | None: ...

    def insert_authenticator(
        self, auth: Authenticator, *, new_principal: Principal | None = None
    ) -> Authenticator: ...


class FilesystemPrincipalStore:
    """DEV-ONLY reference implementation. Rows are plain JSON files under
    `root`, 0600, with a POSIX `flock` around every write and read. This is
    NOT a production identity store and does not pretend to be one: no
    backups, no replication, no migrations, a directory scan away from being
    slow, and `flock` is advisory (and unreliable over NFS) so it only holds
    against processes that go through this class on a local filesystem. It
    exists so the identity core above has something real to run and be
    tested against — including under genuine thread and process concurrency
    — before a real backing store lands.

    One more limit, found 2026-08-01 and not obvious from the flock story
    above: `insert_authenticator` writes two separate files (the forward and
    reverse indexes) under one lock, which closes the race between
    CONCURRENT callers but not a CRASH between the two writes — a process
    killed mid-insert leaves exactly one of the two on disk. The write order
    is chosen so that failure is recoverable-and-inert (an orphaned reverse
    row that only blocks a future bind, never lets one through) rather than
    silent-and-exploitable (two external identities both able to
    authenticate as the same builder_id) — see the comment at the two writes
    themselves for the confirmed exploit this replaced. That is damage
    control on a filesystem that cannot give two files one transaction, not
    a fix — a real backing store closes this properly by making both writes
    one statement, per the `PrincipalStore` Protocol's own requirement.

    Layout:
        principals/<builder_id>.json          the minted identity
        authenticators/<sha256>.json          (provider, external_id) -> builder_id
        by-builder/<builder_id>.json          the reverse UNIQUE index

    The authenticator filename is `sha256(provider \\0 external_id)`, so a
    provider's identifier never becomes a path component even though it has
    already been charset-validated by the time it gets here. Both together,
    not either alone: the hash is what makes traversal impossible, the
    charset check is what keeps a nonsense identifier out of the namespace
    at all. Because the filename is a digest, every read re-checks that the
    row it found actually carries the requested `(provider, external_id)`
    and refuses rather than returning a neighbour's row.
    """

    def __init__(self, root: Path = DEFAULT_PRINCIPAL_ROOT):
        if root.is_symlink():
            raise PrincipalError(f"refusing to use a symlinked principal root: {root}")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._principals = self.root / "principals"
        self._authenticators = self.root / "authenticators"
        self._by_builder = self.root / "by-builder"
        for d in (self._principals, self._authenticators, self._by_builder):
            d.mkdir(exist_ok=True)
            os.chmod(d, 0o700)
        self._lock_path = self.root / ".lock"

    # -- locking ------------------------------------------------------------

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        """One coarse lock for the whole store. A real backing store would
        use a transaction and per-row constraints; a directory of files has
        neither, and a lock that is obviously correct beats a clever scheme
        that is subtly not. Each call opens its own descriptor, so this
        serializes threads within a process as well as separate processes —
        `flock` locks attach to the open file description, not the pid."""
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

    @staticmethod
    def _auth_key(provider: str, external_id: str) -> str:
        # NUL separator so ("git", "hub42") and ("github", "42") can never
        # hash to the same key by concatenation.
        return hashlib.sha256(f"{provider}\x00{external_id}".encode("utf-8")).hexdigest()

    def _principal_path(self, builder_id: str) -> Path:
        return self._principals / f"{_check_builder_id(builder_id)}.json"

    def _auth_path(self, provider: str, external_id: str) -> Path:
        return self._authenticators / f"{self._auth_key(provider, external_id)}.json"

    def _by_builder_path(self, builder_id: str) -> Path:
        return self._by_builder / f"{_check_builder_id(builder_id)}.json"

    # -- io -----------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise PrincipalError(f"store path exists and is not a regular file: {path}")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise PrincipalError(f"store row is corrupt ({path.name}): {e}") from e

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

    def get_principal(self, builder_id: str) -> Principal | None:
        with self._locked(exclusive=False):
            return self._get_principal_unlocked(builder_id)

    def _get_principal_unlocked(self, builder_id: str) -> Principal | None:
        d = self._read_json(self._principal_path(builder_id))
        if d is None:
            return None
        principal = Principal.from_dict(d)
        if principal.builder_id != builder_id:
            raise PrincipalError(
                f"store is inconsistent: principals/{builder_id}.json holds "
                f"builder_id={principal.builder_id!r}"
            )
        return principal

    def get_authenticator(self, provider: str, external_id: str) -> Authenticator | None:
        with self._locked(exclusive=False):
            return self._get_authenticator_unlocked(provider, external_id)

    def _get_authenticator_unlocked(self, provider: str, external_id: str) -> Authenticator | None:
        d = self._read_json(self._auth_path(provider, external_id))
        if d is None:
            return None
        auth = Authenticator.from_dict(d)
        if auth.key() != (provider, external_id):
            # A digest filename means "the file exists" is not the same fact
            # as "this row is the one you asked for" — check, don't assume.
            raise PrincipalError(
                f"store is inconsistent: authenticator row for {provider}/{external_id} "
                f"holds {auth.provider}/{auth.external_id}"
            )
        return auth

    def get_authenticator_for_builder(self, builder_id: str) -> Authenticator | None:
        with self._locked(exclusive=False):
            return self._get_authenticator_for_builder_unlocked(builder_id)

    def _get_authenticator_for_builder_unlocked(self, builder_id: str) -> Authenticator | None:
        d = self._read_json(self._by_builder_path(builder_id))
        if d is None:
            return None
        pointer = Authenticator.from_dict(d)
        if pointer.builder_id != builder_id:
            raise PrincipalError(
                f"store is inconsistent: by-builder/{builder_id}.json holds "
                f"builder_id={pointer.builder_id!r}"
            )
        return pointer

    # -- the one write ------------------------------------------------------

    def insert_authenticator(
        self, auth: Authenticator, *, new_principal: Principal | None = None
    ) -> Authenticator:
        """Atomic under the exclusive lock; see `PrincipalStore` for the
        contract this is implementing. On any conflict nothing is written at
        all — not the authenticator, not the reverse index, and not the
        principal, which is the specific reason a lost first-login race
        leaves no orphan behind."""
        _check_provider(auth.provider)
        _check_external_id(auth.external_id)
        _check_builder_id(auth.builder_id)
        if new_principal is not None and new_principal.builder_id != auth.builder_id:
            raise PrincipalError(
                f"new_principal.builder_id ({new_principal.builder_id!r}) does not match "
                f"the authenticator's builder_id ({auth.builder_id!r})"
            )

        with self._locked(exclusive=True):
            existing = self._get_authenticator_unlocked(auth.provider, auth.external_id)
            if existing is not None:
                return existing  # constraint 1 — including the idempotent same-row case

            blocking = self._get_authenticator_for_builder_unlocked(auth.builder_id)
            if blocking is not None:
                return blocking  # constraint 2 — this builder already has one

            principal = self._get_principal_unlocked(auth.builder_id)
            if new_principal is not None:
                if principal is not None:
                    raise PrincipalError(
                        f"builder_id={auth.builder_id!r} has already been minted — "
                        f"refusing to re-mint over an existing principal"
                    )
                self._write_json(self._principal_path(new_principal.builder_id), new_principal.to_dict())
            elif principal is None:
                raise PrincipalError(
                    f"no principal exists for builder_id={auth.builder_id!r} — "
                    f"refusing to bind an authenticator to an identity the store never minted"
                )

            # Reverse index (by-builder) BEFORE forward index (by-authenticator)
            # — deliberately, not incidentally. These are two files, not one
            # atomic write; a crash between them (not a concurrent caller —
            # flock already closes that race, this is about a process dying
            # mid-write) leaves exactly one of the two on disk. Which one
            # determines what the inconsistency actually costs:
            #   forward-first (the original order): a crash after it leaves
            #     the forward row live with no reverse row, so constraint 2's
            #     check (`_get_authenticator_for_builder_unlocked`) sees
            #     nothing blocking and lets a SECOND, different external
            #     identity bind to the same builder_id — two accounts
            #     silently sharing one identity. Confirmed exploitable
            #     2026-08-01 by simulating exactly this crash point.
            #   reverse-first (this order): the same crash instead leaves an
            #     orphaned reverse row pointing at an authenticator that was
            #     never written. Constraint 2's check still finds it and
            #     still refuses a second bind — the safe direction. The
            #     original external identity can still recover: its next
            #     login finds no forward row, mints a fresh builder_id, and
            #     proceeds normally, leaving the old principal inert rather
            #     than reachable by two accounts.
            # Neither ordering makes the two writes atomic — that still
            # needs a real transaction, which is exactly why this class is
            # DEV-ONLY (see class docstring). This ordering is the one
            # inexpensive thing available on a plain filesystem: pick which
            # single-file failure is recoverable-and-inert instead of
            # silent-and-exploitable.
            self._write_json(self._by_builder_path(auth.builder_id), auth.to_dict())
            self._write_json(self._auth_path(auth.provider, auth.external_id), auth.to_dict())
            return auth

    # -- dev conveniences (not part of the Protocol) ------------------------

    def all_builder_ids(self) -> list[str]:
        with self._locked(exclusive=False):
            return sorted(p.stem for p in self._principals.glob("*.json"))


# ── the identity core ────────────────────────────────────────────────────────

def mint_builder_id() -> str:
    """A new, store-generated identity. `secrets.token_hex` — 128 bits from
    the OS CSPRNG, nothing derived from a caller's input, nothing derived
    from a provider's response, no embedded meaning to parse back out.

    Validated against the same charset that guards every other id here even
    though this function generated it. That is not paranoia theatre: this
    module is the one place a `builder_id` can be born, so it is the one
    place where "every builder_id in the system is path-safe" can be made
    true by construction rather than hoped for — and it is the check that
    would catch a future edit to the generator (a prefix, a uuid with
    dashes, base64 with a `/` in it) before that edit reaches D6's
    `apps/<builder_id>/`. Same belt-and-suspenders posture as
    `plan.py`'s re-validation of `app_name` at the boundary that matters,
    not just at construction."""
    builder_id = secrets.token_hex(_BUILDER_ID_BYTES)
    return _check_builder_id(builder_id)


def lookup_builder_id(store: PrincipalStore, *, provider: str, external_id: str) -> str | None:
    """"Log in as someone who already registered." Returns None — cleanly,
    not by raising — when this external identity has never been seen; "no
    such account yet" is a normal answer on the first-login path, and making
    the caller catch an exception for it would push every caller toward a
    broad `except` that swallows the real refusals too."""
    provider = _check_provider(provider)
    external_id = _check_external_id(external_id)
    auth = store.get_authenticator(provider, external_id)
    if auth is None:
        return None
    if auth.key() != (provider, external_id):
        raise PrincipalError(
            f"store returned an authenticator for {auth.provider}/{auth.external_id} "
            f"when asked for {provider}/{external_id}"
        )
    return auth.builder_id


def bind_authenticator(
    store: PrincipalStore, *, provider: str, external_id: str, builder_id: str,
    now: float | None = None,
) -> Authenticator:
    """Bind `(provider, external_id)` to an ALREADY-MINTED `builder_id`.

    Idempotent for an exact re-bind of the same pair to the same builder —
    a repeated login must not be an error. Anything else raises
    `AuthenticatorConflict`:

      * the pair is already bound to a different `builder_id` (constraint 1;
        this is the "claim someone else's account" case);
      * the `builder_id` already has a different authenticator (constraint
        2, D11 v1's one-authenticator rule; this is the "attach my GitHub
        account to your builder" case).

    Note what constraint 2 means in v1: since a principal only ever comes
    into existence *with* an authenticator (see
    `resolve_verified_identity`), every existing principal already has one,
    so the only call that succeeds here today is the idempotent re-bind.
    That is the intended v1 behaviour, not an accident — this function is
    where re-linking will land once D11's open gap is closed, and where the
    refusal is enforced until then.
    """
    provider = _check_provider(provider)
    external_id = _check_external_id(external_id)
    builder_id = _check_builder_id(builder_id)
    auth = Authenticator(
        provider=provider, external_id=external_id, builder_id=builder_id,
        linked_at=time.time() if now is None else now,
    )
    winner = store.insert_authenticator(auth)
    outcome = _classify(requested=auth, winner=winner)
    if outcome == _INSERTED:
        return _read_back(store, auth)
    raise _conflict(requested=auth, winner=winner, outcome=outcome)


def resolve_verified_identity(
    store: PrincipalStore, *, provider: str, external_id: str, now: float | None = None,
) -> LoginResult:
    """First login, or a returning one — given an ALREADY-VERIFIED external
    identity assertion.

    **The boundary.** This function assumes the caller has already proven
    that the person on the other end of the connection controls
    `(provider, external_id)`. It performs no verification of that claim and
    cannot: there is no token here, no signature, no network call. The real
    caller does not exist yet — it will be the OAuth callback handler that
    validates `state`, exchanges the authorization code for an access token,
    reads the account id off GitHub's `GET /user`, stringifies it, and hands
    it here. Everything on the far side of that (redirect URLs, token
    exchange, scopes, session cookies) is deliberately absent from this
    module; the design doc's Open/next still has real unresolved questions
    about it that need a human decision and credentials, and answering them
    by guessing inside an identity module would be worse than leaving the
    seam visible. Until that handler exists, the only callers are the CLI
    below and the tests — which is exactly the situation
    `FilesystemKeyStore` is in with respect to D7's vault.

    Anyone who *can* call this can log in as anyone. That is not a weakness
    of the identity model; it is the statement that authentication happens
    strictly above this line, and it is why this module is store-side (D1)
    and not something a build in `apps/` can reach.

    **The concurrent-first-login race.** Two requests for the same
    brand-new GitHub account can arrive at once — two web workers, a
    double-clicked login button, a retried callback. The obvious
    implementation (look up, miss, mint, bind) gives each of them a
    different fresh `builder_id`, and then one of them wins the bind while
    the other is left holding an id it already returned to a caller, or —
    worse — that it already wrote a principal row for. The loser's id
    becomes an orphan: a real identity with no way to authenticate into it,
    and possibly with `apps/<builder_id>/` and a signing key already
    provisioned behind it.

    That is not solved here by a lock or a retry loop. It is solved by
    making it unrepresentable: minting is free and local (nothing is
    persisted by `mint_builder_id`), and the principal row is written by the
    store in the *same atomic unit* as the authenticator row, only if the
    authenticator insert actually wins. A loser therefore never wrote
    anything at all — it discards an id that only ever existed in its own
    memory and returns the winner's, with `created=False`. Both requests
    return the same `builder_id`; exactly one reports `created=True`;
    nothing is left behind to clean up. The atomicity requirement lives in
    the `PrincipalStore` Protocol, so a real backing store inherits the
    obligation rather than re-deriving this reasoning.

    The fast path (an existing binding, the overwhelmingly common case)
    still reads first — that read is an optimisation and is allowed to be
    stale, because the insert below is what actually decides.
    """
    provider = _check_provider(provider)
    external_id = _check_external_id(external_id)

    existing = store.get_authenticator(provider, external_id)
    if existing is not None:
        if existing.key() != (provider, external_id):
            raise PrincipalError(
                f"store returned an authenticator for {existing.provider}/{existing.external_id} "
                f"when asked for {provider}/{external_id}"
            )
        return LoginResult(builder_id=existing.builder_id, created=False, authenticator=existing)

    builder_id = mint_builder_id()
    linked_at = time.time() if now is None else now
    auth = Authenticator(
        provider=provider, external_id=external_id, builder_id=builder_id, linked_at=linked_at
    )
    minted = Principal(builder_id=builder_id, minted_at=linked_at)

    winner = store.insert_authenticator(auth, new_principal=minted)
    outcome = _classify(requested=auth, winner=winner)

    if outcome == _INSERTED:
        persisted = _read_back(store, auth)
        if store.get_principal(builder_id) is None:
            raise PrincipalError(
                f"store accepted an authenticator for builder_id={builder_id!r} but did not "
                f"persist the principal row — refusing to report a login that did not happen"
            )
        return LoginResult(builder_id=builder_id, created=True, authenticator=persisted)

    if outcome == _CONFLICT_PAIR:
        # Lost the race (or the fast-path read above was simply stale). This
        # is a normal outcome, not an error: somebody else registered this
        # external identity between our read and our insert, so the answer
        # is *their* builder_id, not a failure.
        persisted = store.get_authenticator(provider, external_id)
        if persisted is None or persisted.builder_id != winner.builder_id:
            raise PrincipalError(
                f"store reported {provider}/{external_id} already bound to "
                f"{winner.builder_id!r} but a read-back does not agree "
                f"({persisted.builder_id if persisted else None!r})"
            )
        if store.get_principal(builder_id) is not None:
            # The orphan this design exists to prevent: a principal row for
            # the id we minted, with no authenticator that can ever reach
            # it. If it is on disk, the store did not do the two writes as
            # one unit and its atomicity guarantee is false.
            raise PrincipalError(
                f"store refused the authenticator insert but still persisted a principal "
                f"row for builder_id={builder_id!r} — that is an orphaned identity and a "
                f"violation of insert_authenticator's atomicity contract"
            )
        return LoginResult(builder_id=persisted.builder_id, created=False, authenticator=persisted)

    if outcome == _CONFLICT_BUILDER:
        # A freshly minted 128-bit id already carrying an authenticator is
        # not a race, it is a broken generator or a broken store. Fail
        # closed rather than handing back an identity that is already
        # someone else's.
        raise PrincipalError(
            f"freshly minted builder_id={builder_id!r} already has an authenticator "
            f"({winner.provider}/{winner.external_id}) — refusing to mint into a collision"
        )

    raise _conflict(requested=auth, winner=winner, outcome=outcome)


# -- insert-outcome handling --------------------------------------------------

_INSERTED = "inserted"
_CONFLICT_PAIR = "conflict_pair"
_CONFLICT_BUILDER = "conflict_builder"
_UNRELATED = "unrelated"


def _classify(*, requested: Authenticator, winner: Authenticator) -> str:
    """Which of the two uniqueness constraints (if either) the store's
    returned row represents. `insert_authenticator` returns the row that
    holds the ground, so this is reading the outcome, not guessing at it."""
    same_pair = winner.key() == requested.key()
    same_builder = winner.builder_id == requested.builder_id
    if same_pair and same_builder:
        return _INSERTED
    if same_pair:
        return _CONFLICT_PAIR
    if same_builder:
        return _CONFLICT_BUILDER
    return _UNRELATED


def _conflict(*, requested: Authenticator, winner: Authenticator, outcome: str) -> PrincipalError:
    if outcome == _CONFLICT_PAIR:
        return AuthenticatorConflict(
            f"{requested.provider}/{requested.external_id} is already bound to "
            f"builder_id={winner.builder_id!r} — refusing to rebind it to "
            f"{requested.builder_id!r}",
            existing=winner,
        )
    if outcome == _CONFLICT_BUILDER:
        return AuthenticatorConflict(
            f"builder_id={requested.builder_id!r} already has an authenticator "
            f"({winner.provider}/{winner.external_id}) — D11 v1 allows exactly one, "
            f"and re-linking is not implemented",
            existing=winner,
        )
    return PrincipalError(
        f"store returned an unrelated row ({winner.provider}/{winner.external_id} -> "
        f"{winner.builder_id!r}) for an insert of {requested.provider}/"
        f"{requested.external_id} -> {requested.builder_id!r}"
    )


def _read_back(store: PrincipalStore, requested: Authenticator) -> Authenticator:
    """Verify the store actually did what it said it did.

    "Verify, don't assert" is a named principle in this repo's designs
    (`safe-app-installer.md`, Nestor's own framing) and it applies to a
    storage backend exactly as much as to a manifest: `insert_authenticator`
    is specified never to overwrite, and a store that quietly did would hand
    back a plausible-looking row having just let one account take over
    another's. Both indexes are checked, because a store that wrote the
    forward row and skipped the reverse one is not enforcing constraint 2 at
    all — and that would only ever show up later, as a takeover that was
    allowed."""
    persisted = store.get_authenticator(requested.provider, requested.external_id)
    if persisted is None or persisted.builder_id != requested.builder_id:
        raise PrincipalError(
            f"store reported binding {requested.provider}/{requested.external_id} -> "
            f"{requested.builder_id!r} but a read-back does not agree "
            f"({persisted.builder_id if persisted else None!r})"
        )
    reverse = store.get_authenticator_for_builder(requested.builder_id)
    if reverse is None or reverse.key() != requested.key():
        raise PrincipalError(
            f"store bound {requested.provider}/{requested.external_id} -> "
            f"{requested.builder_id!r} without a matching reverse index — "
            f"the one-authenticator-per-builder constraint is not being enforced"
        )
    return persisted


# ── CLI ──────────────────────────────────────────────────────────────────────

def _store(args: argparse.Namespace) -> FilesystemPrincipalStore:
    return FilesystemPrincipalStore(Path(args.root))


def _cmd_login(args: argparse.Namespace) -> int:
    """Stands in for the OAuth callback that does not exist yet — it hands
    over a `(provider, external_id)` pair as if a handshake had verified it,
    which on a developer's own machine it obviously has not."""
    try:
        result = resolve_verified_identity(
            _store(args), provider=args.provider, external_id=args.external_id
        )
    except PrincipalError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({
        "builder_id": result.builder_id,
        "created": result.created,
        "authenticator": result.authenticator.to_dict(),
    }, indent=2, sort_keys=True))
    return 0


def _cmd_lookup(args: argparse.Namespace) -> int:
    try:
        builder_id = lookup_builder_id(
            _store(args), provider=args.provider, external_id=args.external_id
        )
    except PrincipalError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if builder_id is None:
        print("(not registered)")
        return 1
    print(builder_id)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        principal = store.get_principal(args.builder_id)
        auth = store.get_authenticator_for_builder(args.builder_id)
    except PrincipalError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if principal is None:
        print(f"no such builder_id: {args.builder_id!r}", file=sys.stderr)
        return 1
    print(json.dumps({
        "principal": principal.to_dict(),
        "authenticator": auth.to_dict() if auth else None,
    }, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="principal.py")
    p.add_argument("--root", default=str(DEFAULT_PRINCIPAL_ROOT))
    sub = p.add_subparsers(dest="command", required=True)

    lg = sub.add_parser("login", help="first login or returning login for a verified external identity")
    lg.add_argument("--provider", required=True)
    lg.add_argument("--external-id", required=True)
    lg.set_defaults(func=_cmd_login)

    lk = sub.add_parser("lookup", help="builder_id for an already-registered external identity")
    lk.add_argument("--provider", required=True)
    lk.add_argument("--external-id", required=True)
    lk.set_defaults(func=_cmd_lookup)

    sh = sub.add_parser("show", help="the principal row and its authenticator")
    sh.add_argument("builder_id")
    sh.set_defaults(func=_cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
