#!/usr/bin/env python3
"""stores/checkpoint_memory.py — per-builder checkpoint memory (D9/D12,
docs/design/the-forge.md).

D9 names the mechanic: D8's Socratic checkpoint ("confirm a design decision,
demonstrate you understood the tradeoff") is a seventh row in
`VISION.md`'s Pattern 2 verification-as-learning loop. D12 says: build the
memory half of that loop by adopting Nestor itself, not a pattern reference —
`EntityResolver(store, domain=f"builder:{builder_id}")` over one Nestor
`SqliteStore` per `builder_id`. **This module is that storage/memory layer
only.** It does not ask a builder anything, render a checkpoint UI, or decide
where "a decision" starts (D8's own open question) — see "Not in scope"
below. What it gives a future D8 implementation is the primitive: has builder
X sealed decision-type Y before, and if so, record a new seal / check a
match / handle a rejection.

Store-side authority (D1), same directory and same trust level as
`principal.py` and `session.py`: a builder's calibration record — what they
have actually demonstrated understanding of — is exactly the kind of trust
state a sandboxed build in `apps/` has no business reading or writing about
itself (a build attesting to its own trustworthiness is not attestation).
`apps/the-forge/` never imports this module.

**Storage isolation: one Nestor `SqliteStore` file per `builder_id`, not
domain-tag scoping inside one shared database — decided 2026-08-01 in the
design doc, and load-bearing here.** Nestor's own `domain=` keyword argument
would happily give two builders separate rows inside ONE shared database file
if the caller passed distinct domain strings for each. That works right up
until it doesn't: the whole isolation guarantee would then rest on this
module (or something upstream of it) never mis-scoping a domain string. A
single wrong f-string, a copy-pasted call site, a `builder_id` that collides
after some future normalization step — any of those becomes cross-builder
data exposure, silently, because the shared database has no boundary of its
own to catch it. A directory-per-builder file layout removes that failure
mode by construction rather than by discipline: `checkpoint_db_path` maps
`builder_id -> its own file`, so a mis-scoped domain STRING can still misfile
*within* that one builder's own memory (a bug, but a contained one — see
`test_checkpoint_memory.py`'s adversarial section for what this module does
to make that structurally hard to get wrong), but it has no other builder's
file to reach at all. This is the same directory-per-builder boundary D6
already uses for `apps/<builder_id>/`, applied one layer over.

Decision-type scoping lives INSIDE that per-builder file, as a Nestor
`domain` string — `f"builder:{builder_id}:decision:{decision_type}"` — not a
second directory layer. D9's own line is explicit about the shape this needs:
"the seal domain must be `(builder_id, decision_type)`, never just
decision_type globally." Folding both into one domain string is what makes
that literally true, and doing it inside the per-builder file (rather than
one-file-per-decision-type) is safe precisely because file-per-builder
already closed the cross-builder case above — the only thing a mis-scoped
decision-type substring can now do is misfile two of *this builder's own*
decision types against each other, never leak into someone else's file. The
alternative the design doc's recipe section names — a dedicated
source/target language-pair per decision-type instead of folding it into
`domain` — was not taken here because `EntityResolver.__init__` exposes a
single `domain` parameter (it sets both `source_lang` and `target_lang` to
it internally); reaching past `EntityResolver` into `nestor.memory.add_pair`
directly to get independent language tags would mean re-implementing pieces
of the recipe `EntityResolver` already gives for free, for no isolation
benefit the domain string doesn't already provide.

**Nestor's audit ledger is deliberately NOT split per builder.** Every
`EntityResolver.seal` / `reject_match` / `reject_pair` call appends to
Nestor's own hash-chained ledger (`nestor.cascade`, D10's "Pedagogy ledger,"
`Nestor, per-builder domain / written by Nestor's memory/cascade on every
checkpoint seal/reject"). "Per-builder domain" there describes the domain TAG
recorded in each entry, not a separate ledger file — D12's storage-isolation
decision is scoped to the `SqliteStore` (the thing a mis-scoped string could
turn into a data leak), not to the ledger (an append-only audit trail, where
every entry already carries its own domain and a shared chain is a feature —
one auditor-facing trail, not one per builder to reconcile). Left at Nestor's
own default, that ledger path is `data/ledger.jsonl` *relative to the
process's current working directory* — exactly the kind of cwd-dependent
default this repo's other dev-only stores (`.principals/`, `.sessions/`)
avoid by rooting themselves next to `stores/` instead. `open_checkpoint_memory`
below points Nestor's ledger at `<root>/ledger.jsonl` (via
`nestor.cascade.set_ledger_path`) so running this module's tests, or a real
caller, does not scribble a `data/` directory into whatever directory the
process happened to be started from. That call is process-global (Nestor's
ledger is a process-wide path, same as its `storage.set_store` global) —
callers that need a different ledger location for their own reasons should
call `nestor.cascade.set_ledger_path` themselves afterwards; this module only
sets a sane default once, on first use.

**Real packaging fact, load-bearing for `stores/requirements.txt`:**
`pip index versions nestor` returns "No matching distribution found" —
Nestor is not published to PyPI. It is a sibling repo
(`github.com/rudi193-cmd/Nestor`), consumed the way `apps/semantic-translator`
already consumes it in this very repo's `pyproject.toml`: a git dependency,
pinned at a SHA at PROMOTION time (see `requirements.txt`'s comment for the
one correction this module makes to the design doc's own "pip install
nestor" phrasing). For local dev/testing against this module right now:
`pip install -e /workspace/nestor` (or wherever the sibling checkout resolves
in your environment — verify the path yourself, it is not guaranteed).
`tests/test_checkpoint_memory.py`'s module docstring states this plainly,
the same honest-environment-disclosure convention
`apps/the-forge/tests/test_sandbox_runner.py` uses for its own "no bwrap in
this container" note.

Not in scope, deliberately — the boundary this module stops at:
  * D8's actual Socratic checkpoint UX — the question a builder sees, the
    follow-up that tests whether they understood (not just picked an
    option), the "lighter-touch confirm" prompt copy. All undesigned UX
    work. This module gives a future D8 implementation exactly one
    primitive per operation (has-sealed / seal / reject_match / reject_pair)
    and nothing about how or when to call it.
  * Deciding what counts as "a decision" worth checkpointing at all — named
    in the design doc's own Open/next as a real unresolved question, not
    something to guess at here.
  * `nestor calibrate` / `Curator.rejection_signals()` — the design doc's
    recipe section names both as reachable extensions on the same store this
    module opens, but neither is a checkpoint-memory PRIMITIVE the way
    seal/check/reject are; a caller that wants them can open the same
    `SqliteStore` this module's `checkpoint_db_path` computes and hand it to
    `nestor.curator.Curator` directly.
  * The py-fsrs review-scheduling half of D9 ("is it due for review") — D12
    is explicit that Nestor answers "has this been sealed" and py-fsrs
    answers "is it due", with no overlap between the two. This module is
    entirely the Nestor half.
  * `NESTOR_SEAL_KEY` / a keyring (Nestor's own seal-signature machinery,
    `nestor.signing`). Left at Nestor's documented default — unset, signing
    off, every `status='sealed'` row trusted — the same "opt-in,
    backward-compatible" default Nestor itself ships. D4 already owns key
    custody for this ecosystem (the Fernet vault, per the design doc's
    Open/next); wiring the checkpoint memory's own seals to it is a D4/D12
    integration decision for whoever builds D8, not something to default
    into silently here. `nestor calibrate` and a real key are both later
    hardening, not part of this module's job.

Usage (dev CLI, mirroring principal.py / session.py's shape):
    python stores/checkpoint_memory.py has-sealed <builder_id> <decision_type>
    python stores/checkpoint_memory.py seal <builder_id> <decision_type> \\
        --surface "..." --canonical "..."
    python stores/checkpoint_memory.py reject-match <builder_id> <decision_type> \\
        --surface "..." --pair-id <id> --reason "..."
    python stores/checkpoint_memory.py reject-pair <builder_id> <decision_type> \\
        --pair-id <id> --reason "..."
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_CHECKPOINT_ROOT = Path(__file__).resolve().parent / ".checkpoints"

# Same charset rule `principal.py` defines and `session.py` re-uses rather
# than re-implementing — see both modules' docstrings. `decision_type` is not
# a filesystem path component the way `builder_id` is (it never becomes part
# of a file's name; it becomes a substring of a Nestor `domain` string that
# lives inside SQLite rows), but the same "an identifier that could end up
# formatted into a scoping key deserves the same discipline as one that ends
# up in a path" reasoning `principal.py` states for `provider`/`external_id`
# applies here: a `decision_type` containing `builder:`/`:decision:` or a NUL
# byte could otherwise be crafted to make one domain string collide with
# another builder's own *literal* domain string — not a cross-builder file
# read (the one-file-per-builder boundary already rules that out
# structurally, see module docstring), but worth closing anyway rather than
# leaving it as a theoretical misfile.
_DECISION_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX_DECISION_TYPE_LEN = 128

# The Nestor `domain` string a given (builder_id, decision_type) resolves to.
# Folds both into one domain per D9's own line: "the seal domain must be
# (builder_id, decision_type), never just decision_type globally" — see
# module docstring for why this is safe to do as one domain string rather
# than a second directory layer.
_DOMAIN_TEMPLATE = "builder:{builder_id}:decision:{decision_type}"

# ── import principal.py the way session.py already does ────────────────────
#
# spec_from_file_location, not a package-relative import: stores/ has no
# __init__.py and is run as a directory of standalone scripts, same reason
# session.py's own comment gives. `_check_builder_id` is imported directly
# rather than re-implemented — principal.py is the one place a builder_id's
# path-safety charset is defined, and this module's own directory-per-builder
# guarantee (see module docstring) depends on every builder_id that reaches
# `checkpoint_db_path` having already passed that exact check.
_REPO = Path(__file__).resolve().parent.parent
_principal_spec = importlib.util.spec_from_file_location(
    "principal", Path(__file__).resolve().parent / "principal.py"
)
principal = importlib.util.module_from_spec(_principal_spec)
sys.modules["principal"] = principal
_principal_spec.loader.exec_module(principal)

_principal_check_builder_id = principal._check_builder_id


# ── import Nestor ────────────────────────────────────────────────────────────
#
# A real, informative failure if Nestor is not on the path, rather than a
# bare ImportError a future maintainer has to go spelunking for. See the
# module docstring's "Real packaging fact" section and stores/requirements.txt.
try:
    from nestor import cascade as _nestor_cascade
    from nestor import memory as _nestor_memory
    from nestor.entity import EntityResolver as _EntityResolver
    from nestor.sqlite_store import SqliteStore as _SqliteStore
except ImportError as _e:  # pragma: no cover — exercised by a real missing-dep env
    raise ImportError(
        "stores/checkpoint_memory.py requires Nestor, which is NOT on PyPI "
        "(see this module's docstring and stores/requirements.txt). For "
        "local dev/testing, install it editable from the sibling checkout: "
        "`pip install -e /workspace/nestor` (verify that path exists in your "
        "environment first — `ls /workspace/nestor`). For a real deployment, "
        "install from the pinned git SHA in stores/requirements.txt once one "
        "is recorded at promotion time."
    ) from _e


class CheckpointMemoryError(Exception):
    """Fail-closed refusal — bad `builder_id`/`decision_type`, a Nestor-level
    exception this module caught at its boundary, or a store that did not
    honor its own contract. Every refusal in this module raises this (or a
    subclass); nothing returns a bool a caller could forget to check.

    This is the "one exception type at the call site" `session.py`'s own
    docstring names for its own `principal.py` import, applied to Nestor:
    `nestor.sqlite_store.StoreClosedError`, `nestor.ledger.LedgerError`,
    `nestor.memory.ConflictingSealError` and `nestor.memory.RejectedPairError`
    are all real, well-formed exceptions a correctly-used Nestor raises on
    purpose — but a caller of THIS module should not have to import Nestor
    itself just to catch its exception types. See `CheckpointConflict` and
    `CheckpointRejected` below for the two Nestor refusals worth preserving
    as a distinct subclass (mirroring `principal.py`'s own
    `AuthenticatorConflict`, which does the same thing for a store
    conflict); every other Nestor-level exception is wrapped as a plain
    `CheckpointMemoryError`.
    """


class CheckpointConflict(CheckpointMemoryError):
    """Wraps `nestor.memory.ConflictingSealError`: a different verifier
    already sealed a different answer for this exact decision wording.
    Carries no override decision of its own — a caller that wants to proceed
    anyway passes `override_conflict=True` to `CheckpointMemory.seal`, the
    same override Nestor itself exposes."""


class CheckpointRejected(CheckpointMemoryError):
    """Wraps `nestor.memory.RejectedPairError`: this decision wording was
    previously rejected and will not be re-sealed implicitly. A caller that
    wants to proceed anyway passes `override_rejection=True`."""


# ── validation ───────────────────────────────────────────────────────────────

def _check_builder_id(builder_id: Any) -> str:
    """Delegates to `principal.py`'s own `_check_builder_id` — not
    re-implemented here, see module docstring — but re-raises as
    `CheckpointMemoryError` so every refusal this module produces is the
    same exception type regardless of which validator underneath actually
    caught the problem. Exact same shape as `session.py`'s own
    `_check_builder_id` wrapper."""
    try:
        return _principal_check_builder_id(builder_id)
    except principal.PrincipalError as e:
        raise CheckpointMemoryError(f"builder_id rejected: {e}") from e


def _check_decision_type(decision_type: Any) -> str:
    if not isinstance(decision_type, str):
        raise CheckpointMemoryError(
            f"decision_type must be a str, got {type(decision_type).__name__}"
        )
    if not decision_type or not _DECISION_TYPE_PATTERN.match(decision_type):
        raise CheckpointMemoryError(
            f"decision_type {decision_type!r} fails the path-safety-derived "
            f"charset (see module docstring)"
        )
    if len(decision_type) > _MAX_DECISION_TYPE_LEN:
        raise CheckpointMemoryError(
            f"decision_type is longer than {_MAX_DECISION_TYPE_LEN} characters"
        )
    return decision_type


def _domain(builder_id: str, decision_type: str) -> str:
    return _DOMAIN_TEMPLATE.format(builder_id=builder_id, decision_type=decision_type)


# ── the one-file-per-builder path ───────────────────────────────────────────

def checkpoint_db_path(builder_id: str, root: Path = DEFAULT_CHECKPOINT_ROOT) -> Path:
    """The one Nestor `SqliteStore` file for `builder_id`. Computes a path
    only — does not create the file, the directory, or touch the
    filesystem at all, matching `principal.py`'s `_principal_path` /
    `session.py`'s `_session_path`, which do the same.

    **Why this is structurally impossible to cross a builder boundary with,**
    restated as code rather than prose (see module docstring for the design
    reasoning):

      1. `builder_id` is validated by `_check_builder_id` BEFORE it ever
         touches this function's return value — the same charset
         `principal.py` already enforces makes `builder_id` a single path
         component with no `/`, no leading `.`/`..` traversal segment
         (`_ID_PATTERN` requires an alnum first character), and no NUL byte.
         A `builder_id` that fails this raises before a `Path` is even built.
      2. The resulting filename is `f"{builder_id}.db"` — a FIXED suffix
         appended to the (now validated, `/`-free) `builder_id` string
         itself. Because the suffix is constant, the map `builder_id ->
         filename` is injective: two DIFFERENT validated `builder_id`
         strings cannot produce the same filename (their raw content would
         already have to be equal, since appending the same suffix to two
         unequal strings never re-equalizes them), and one builder_id cannot
         be crafted to *resolve into* another's file by adding a suffix of
         its own — the suffix is not attacker-controlled at all.
      3. `root` is a single, non-attacker-controlled directory (the caller's
         own `stores/.checkpoints/` by default) — `builder_id` never
         contributes more than the one final path component this function
         appends.

    `tests/test_checkpoint_memory.py`'s adversarial section tries to break
    exactly this — see its module docstring.
    """
    builder_id = _check_builder_id(builder_id)
    root = Path(root)
    if root.is_symlink():
        raise CheckpointMemoryError(f"refusing to use a symlinked checkpoint root: {root}")
    return root / f"{builder_id}.db"


# ── the checkpoint memory itself ────────────────────────────────────────────
#
# A class, not a set of free functions — deliberately the `session.py`
# `FilesystemSessionStore` shape rather than `principal.py`'s "Store object +
# free functions operating on it" shape, and for a reason specific to this
# module: `principal.py` and `session.py`'s free functions each take a
# caller-supplied Store and do one atomic operation against it, with no
# state of their own to manage between calls. This module instead has to
# hold open a real SQLite connection (via `SqliteStore`) across a sequence of
# calls — has_sealed, then maybe seal, then maybe reject_match — because
# re-opening the file per call would be wasteful and because
# `EntityResolver` itself is a small stateful wrapper around one open store.
# That is a resource with a lifecycle (open, use, close), the same shape
# `FilesystemPrincipalStore`/`FilesystemSessionStore` already are, so
# `CheckpointMemory` follows their class-with-`close()` shape instead of
# `principal.py`'s free-function layer above them. Use it as a context
# manager (`with open_checkpoint_memory(...) as cm:`) or call `.close()`
# explicitly — never let it be garbage-collected with the store still open.

class CheckpointMemory:
    """One builder's checkpoint memory for one decision-type — the D8
    primitive: has builder X sealed decision-type Y before, and if so,
    record a new seal / check a match / handle a rejection.

    Do not construct directly; use `open_checkpoint_memory` (below), which
    validates its inputs the same way `checkpoint_db_path` does before this
    class ever opens a file — constructing this class with an unvalidated
    `builder_id`/`decision_type` is a programming error in a caller within
    this module, not something an external caller should be doing.
    """

    def __init__(self, builder_id: str, decision_type: str, store: "_SqliteStore"):
        self.builder_id = builder_id
        self.decision_type = decision_type
        self.domain = _domain(builder_id, decision_type)
        self._store = store
        try:
            self._resolver = _EntityResolver(self._store, domain=self.domain)
        except Exception as e:  # noqa: BLE001 — boundary: see CheckpointMemoryError
            self._store.close()
            raise CheckpointMemoryError(
                f"failed to open checkpoint memory for builder_id={builder_id!r} "
                f"decision_type={decision_type!r}: {type(e).__name__}: {e}"
            ) from e

    # -- the D8 trigger -----------------------------------------------------

    def has_sealed(self) -> bool:
        """Whether this builder has sealed ANY decision under this
        `decision_type` — D8's "lighter-touch confirm" trigger at the
        decision-TYPE granularity (as opposed to `check`, below, which
        matches one specific decision's wording). Deliberately does not go
        through `EntityResolver.resolve`'s fuzzy matching: this is a
        domain-wide "has this builder ever engaged this decision-type at
        all" question, and answering it by scanning this decision-type's own
        sealed rows is both simpler and immune to threshold tuning — no
        wording, however different, needs to score above `SEAL_THRESHOLD`
        against something else in the same domain for this to say True.
        """
        try:
            candidates = self._store.memory_candidates(self.domain, self.domain)
            return any(_nestor_memory.is_verified_seal(row) for row in candidates)
        except Exception as e:  # noqa: BLE001 — boundary
            raise self._wrap(e) from e

    def check(self, decision_description: str) -> dict:
        """The fine-grained sibling of `has_sealed`: does THIS specific
        decision wording resolve to a sealed match in this decision-type's
        memory. Thin wrapper over `EntityResolver.resolve` — see its
        docstring for the returned shape (`canonical`, `confidence`,
        `sealed`, `provenance`). This is D12's own recipe line, restated:
        "a hit at/above threshold triggers D8's lighter-touch confirm, a
        miss or near-miss triggers the full Socratic checkpoint."
        """
        try:
            return self._resolver.resolve(decision_description)
        except Exception as e:  # noqa: BLE001 — boundary
            raise self._wrap(e) from e

    # -- sealing --------------------------------------------------------------

    def seal(
        self,
        decision_description: str,
        chosen_option_and_rationale: str,
        *,
        verifier: str | None = None,
        weight: float = 1.0,
        origin: str = "",
        override_conflict: bool = False,
        override_rejection: bool = False,
    ) -> dict:
        """Record that this builder has answered a checkpoint and
        demonstrated they understood the tradeoff — `surface` is the
        decision description (D8's prompt), `canonical` is the chosen
        option plus the rationale a future lighter-touch confirm should be
        able to show back to the builder. `verifier` defaults to this
        builder's own `builder_id`: a builder sealing their own checkpoint
        answer is exactly what D9's "this builder's grasp of the pattern"
        record means to capture, not a third party vouching for them (that
        is D4's manifest-signing gate, a different system — see D10).
        """
        verifier = self.builder_id if verifier is None else verifier
        try:
            return self._resolver.seal(
                decision_description,
                chosen_option_and_rationale,
                verifier=verifier,
                weight=weight,
                origin=origin,
                override_conflict=override_conflict,
                override_rejection=override_rejection,
            )
        except _nestor_memory.ConflictingSealError as e:
            raise CheckpointConflict(str(e)) from e
        except _nestor_memory.RejectedPairError as e:
            raise CheckpointRejected(str(e)) from e
        except Exception as e:  # noqa: BLE001 — boundary
            raise self._wrap(e) from e

    # -- rejection: both reachable, not just sealing -------------------------

    def reject_match(
        self,
        decision_description: str,
        *,
        pair_id: str = "",
        target_text: str = "",
        verifier: str | None = None,
        reason: str = "",
    ) -> dict:
        """"That explanation didn't fit THIS specific case" — D12's own
        framing. Suppresses `decision_description` as a query for the named
        pair (`pair_id`) or draft (`target_text`); the pair itself, and
        everything else that resolves to it, is untouched. Requires at
        least one of `pair_id`/`target_text`, same as
        `nestor.memory.reject_match` itself."""
        verifier = self.builder_id if verifier is None else verifier
        try:
            return _nestor_memory.reject_match(
                decision_description,
                self.domain,
                self.domain,
                pair_id=pair_id,
                target_text=target_text,
                verifier=verifier,
                reason=reason,
                store=self._store,
            )
        except ValueError:
            # nestor.memory.reject_match's own "neither pair_id nor
            # target_text given" refusal — a caller error, not a Nestor
            # internal failure, so it is worth its own message rather than
            # being folded into the generic wrap below.
            raise CheckpointMemoryError(
                "reject_match needs pair_id or target_text — otherwise there "
                "is nothing to suppress"
            ) from None
        except Exception as e:  # noqa: BLE001 — boundary
            raise self._wrap(e) from e

    def reject_pair(
        self, pair_id: str, *, verifier: str | None = None, reason: str = ""
    ) -> None:
        """"I was wrong about this generally, unseal it everywhere" —
        D12's own framing. Retires `pair_id` itself: never served, never
        offered as a match, for ANY query, in this decision-type's memory.
        Use `reject_match` instead when the pair is right in general but
        wrong for one specific query."""
        verifier = self.builder_id if verifier is None else verifier
        try:
            _nestor_memory.reject_pair(pair_id, verifier=verifier, reason=reason, store=self._store)
        except Exception as e:  # noqa: BLE001 — boundary
            raise self._wrap(e) from e

    # -- cleanup --------------------------------------------------------------

    def close(self) -> None:
        """Checkpoint the underlying SQLite WAL and retire the connection —
        see `SqliteStore.close`. Idempotent: `SqliteStore.close` already is,
        and this does not add a second layer of state to get out of sync
        with it."""
        self._store.close()

    def __enter__(self) -> "CheckpointMemory":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- boundary --------------------------------------------------------------

    def _wrap(self, e: Exception) -> CheckpointMemoryError:
        """Every Nestor-level exception this module has not already given
        its own subclass (`CheckpointConflict`, `CheckpointRejected`) lands
        here, wrapped as a plain `CheckpointMemoryError` — `StoreClosedError`
        (used the connection after `close()`), `LedgerError` (Nestor's
        hash-chained audit trail refused the write — see module docstring's
        `set_ledger_path` note), or anything else Nestor's own boundary was
        not specifically named for. A caller of this module catches
        `CheckpointMemoryError` and never needs to `import nestor` to know
        what hit it."""
        if isinstance(e, CheckpointMemoryError):
            return e
        return CheckpointMemoryError(f"{type(e).__name__}: {e}")


# Point Nestor's ledger at this module's own root instead of its
# cwd-relative `data/ledger.jsonl` default. See module docstring's "Nestor's
# audit ledger is deliberately NOT split per builder" section for why this
# is a single shared path, not one per builder, and why it is safe for this
# to be process-global the same way `nestor.cascade.set_ledger_path` itself
# is.
#
# Called on every `open_checkpoint_memory`, not gated to "once per
# process": `cascade.set_ledger_path` is already idempotent for a REPEATED
# path (it only drops Nestor's in-process verify/checkpoint cache when the
# path actually changes — see its own docstring), so the common case — every
# caller in a process uses the same `root` — costs nothing extra. Gating it
# to "once" would instead have been actively wrong: it would silently pin
# every later call's ledger to whichever `root` happened to be passed
# FIRST, which is exactly backwards for anything that legitimately opens
# more than one root in a process — including this module's own test suite,
# which gives each test its own `tmp_path`.
def _point_ledger_at(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _nestor_cascade.set_ledger_path(root / "ledger.jsonl")


def open_checkpoint_memory(
    builder_id: str,
    decision_type: str,
    *,
    root: Path = DEFAULT_CHECKPOINT_ROOT,
) -> CheckpointMemory:
    """Open (creating if absent) `builder_id`'s own checkpoint-memory file,
    scoped to `decision_type`. Fail-closed on a malformed `builder_id` or
    `decision_type` BEFORE any file is created — same "no file left behind
    on hostile input" discipline `mount_policy.py`'s `write_scoped_policy`
    and `session.py`'s validation already follow (both validate before
    touching the filesystem, not after).

    Returns a `CheckpointMemory` the caller must `close()` — or, better,
    use as a context manager:

        with open_checkpoint_memory(builder_id, "auth-flow-for-user-facing-form") as cm:
            if not cm.has_sealed():
                ...  # full Socratic checkpoint
    """
    builder_id = _check_builder_id(builder_id)
    decision_type = _check_decision_type(decision_type)
    root = Path(root)
    if root.is_symlink():
        raise CheckpointMemoryError(f"refusing to use a symlinked checkpoint root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    _point_ledger_at(root)

    db_path = checkpoint_db_path(builder_id, root=root)
    try:
        store = _SqliteStore(str(db_path))
    except Exception as e:  # noqa: BLE001 — boundary
        raise CheckpointMemoryError(
            f"failed to open checkpoint store at {db_path}: {type(e).__name__}: {e}"
        ) from e
    # `SqliteStore.__init__` does NOT create the file for a file-backed
    # store — the connection (and therefore the file) is lazily opened on
    # first use, which `CheckpointMemory.__init__` triggers via
    # `EntityResolver`'s own `store.memory_init()` call. The chmod has to
    # happen AFTER that construction, not before — chmod-ing here, before
    # the file exists, would silently no-op and leave the row on disk at
    # sqlite3's own default mode (typically 0644, readable by anyone who
    # can read `root/`) instead of the 0600 every other dev-only store in
    # this directory (`.principals/`, `.sessions/`) uses. Found by testing
    # this exact ordering while writing this function, not assumed.
    opened = CheckpointMemory(builder_id, decision_type, store)
    if db_path.exists():
        os.chmod(db_path, 0o600)
    return opened


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_has_sealed(args: argparse.Namespace) -> int:
    try:
        with open_checkpoint_memory(args.builder_id, args.decision_type, root=Path(args.root)) as cm:
            sealed = cm.has_sealed()
    except CheckpointMemoryError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"has_sealed": sealed}))
    return 0 if sealed else 1


def _cmd_seal(args: argparse.Namespace) -> int:
    try:
        with open_checkpoint_memory(args.builder_id, args.decision_type, root=Path(args.root)) as cm:
            result = cm.seal(args.surface, args.canonical, verifier=args.verifier)
    except CheckpointMemoryError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_reject_match(args: argparse.Namespace) -> int:
    try:
        with open_checkpoint_memory(args.builder_id, args.decision_type, root=Path(args.root)) as cm:
            result = cm.reject_match(
                args.surface, pair_id=args.pair_id or "", target_text=args.target or "",
                verifier=args.verifier, reason=args.reason or "",
            )
    except CheckpointMemoryError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_reject_pair(args: argparse.Namespace) -> int:
    try:
        with open_checkpoint_memory(args.builder_id, args.decision_type, root=Path(args.root)) as cm:
            cm.reject_pair(args.pair_id, verifier=args.verifier, reason=args.reason or "")
    except CheckpointMemoryError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print("rejected")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_memory.py")
    p.add_argument("--root", default=str(DEFAULT_CHECKPOINT_ROOT))
    sub = p.add_subparsers(dest="command", required=True)

    hs = sub.add_parser("has-sealed", help="has this builder sealed this decision-type")
    hs.add_argument("builder_id")
    hs.add_argument("decision_type")
    hs.set_defaults(func=_cmd_has_sealed)

    sl = sub.add_parser("seal", help="seal a new decision for this builder/decision-type")
    sl.add_argument("builder_id")
    sl.add_argument("decision_type")
    sl.add_argument("--surface", required=True, help="decision description")
    sl.add_argument("--canonical", required=True, help="chosen option + rationale")
    sl.add_argument("--verifier", default=None, help="defaults to builder_id")
    sl.set_defaults(func=_cmd_seal)

    rm = sub.add_parser("reject-match", help="this application was wrong; pattern still holds")
    rm.add_argument("builder_id")
    rm.add_argument("decision_type")
    rm.add_argument("--surface", required=True, help="decision description being rejected")
    rm.add_argument("--pair-id", default=None)
    rm.add_argument("--target", default=None)
    rm.add_argument("--verifier", default=None)
    rm.add_argument("--reason", default=None)
    rm.set_defaults(func=_cmd_reject_match)

    rp = sub.add_parser("reject-pair", help="the pattern itself was wrong; unseal everywhere")
    rp.add_argument("builder_id")
    rp.add_argument("decision_type")
    rp.add_argument("pair_id")
    rp.add_argument("--verifier", default=None)
    rp.add_argument("--reason", default=None)
    rp.set_defaults(func=_cmd_reject_pair)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
