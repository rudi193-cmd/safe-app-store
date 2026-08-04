"""nestor_seam.py — the ONLY place this face touches Nestor.

DRAFT. Destination: ``homestead-affairs/homestead`` → ``homestead/keep/nestor_seam.py``.
Written contract-first per ``docs/conventions/pinned-dependency-seams.md``:
the seam and its contract exist before any call site, so the boundary is built
before there is anything to drift across. Nothing is imported yet — the stubs
below raise until the pin is chosen and the store implementation exists.

Nestor is Apache-2.0 with ``dependencies = []``. Nothing here obliges a
household to install a dependency tree.

═══════════════════════════════════════════════════════════════════════════
TAKEN FROM NESTOR   (pin: TBD — a tag or sha, never a branch)
═══════════════════════════════════════════════════════════════════════════

  EntityResolver(store, domain=..., seal_threshold=...)   nestor.entity
      .resolve(surface) -> dict      read-only; fuzzy-match a surface form
                                     against sealed aliases
      .seal(surface, canonical, verifier=...)             human-initiated write
      .add_alias(surface, canonical, verifier=...)        human-initiated write

  Storage                                                 nestor.storage
      A Protocol. We implement it over our own SQLite. Nestor owns no
      persistence — "a concrete implementation is *injected* by the host."

  set_ledger_override(path)                               nestor.cascade
      REQUIRED. See PRECONDITIONS.

  ledger.head() / ledger.verify(expected_head=...)        nestor.ledger
      Verify our own chain on read/boot. A broken chain is a refusal.

═══════════════════════════════════════════════════════════════════════════
NOT TAKEN   (deliberate — the omissions carry as much weight as the takings)
═══════════════════════════════════════════════════════════════════════════

  nestor.cascade translation pipeline   translate_text, translate_segment,
      graduate_segment. Translation is not this face's domain.

  nestor.matcher / nestor.semantic_matcher   reached only through
      EntityResolver. Never imported directly; that is how the surface widens.

  nestor.serve / nestor.ui / nestor.ui_page   an HTTP server. ``ui.py`` imports
      ``http.server`` and ``urllib.parse`` at module level, which would put a
      network import in the import-pure core and fail ``import_pure_core [M]``.

  nestor.answer · curator · frank · glossary · langid · segment · reconcile
      · calibrate · portable · keyring · signing · memory · embedding_store
      · sqlite_store · engine · cli
      Not our business. Some are excellent. Not ours.

  THE ``cloud`` EXTRA  (``anthropic``)  — MUST NEVER BE INSTALLED ON THIS FACE.
      This face's premise is that nothing leaves the device. Installing this
      extra anywhere in the dependency chain contradicts the product.

  THE ``semantic`` EXTRA  (``fastembed``) — license discrepancy: its ``license``
      field says Apache while its PyPI classifier says ``Other/Proprietary``
      (see ``apps/law-gazelle/docs/sourcing_report.md``). Unresolved, so unused.
      Local embeddings come from Ollama's ``/api/embed``, which is already a
      dependency of this face.

═══════════════════════════════════════════════════════════════════════════
PRECONDITIONS   — all three MUST hold before any Nestor call in this process
═══════════════════════════════════════════════════════════════════════════

1.  THE LEDGER IS PINNED INSIDE /.homestead.

    This is the one that is easy to miss and expensive to miss. Nestor's
    hash-chained ledger is **not part of the Storage protocol** — injecting the
    store does not cover it. It resolves independently:

        _LEDGER_OVERRIDE  →  $NESTOR_LEDGER  →  "data/ledger.jsonl"

    So a default install writes to ``data/ledger.jsonl`` relative to the
    working directory: outside the household root, outside anything the
    vault-leak lint would bless.

    And ``EntityResolver.resolve()`` appends on EVERY call (``entity.py:152``):

        {"kind": "entity_resolve",
         "surface_sha": sha256(surface)[:16],   # input, hashed
         "canonical":   <resolved value>,       # OUTPUT, IN CLEARTEXT
         "sealed": ..., "confidence": ...}

    The input is hashed; the resolved value is not. In a legal matter that is a
    line recording, in the clear, that some surface form resolves to a named
    party. Local, but recorded — and by default recorded somewhere this face's
    own rules do not reach.

    Two notes on that hash, so nobody mistakes it for protection: it is SHA-256
    truncated to 16 hex characters (64 bits) and unsalted. Against low-entropy
    inputs such as personal names it is dictionary-reversible. ``surface_sha``
    is an audit identifier, not a privacy control.

    None of this is a defect in Nestor. The ledger is the audit trail; it is
    *meant* to live outside the store it audits, and that is correct design for
    Nestor. It simply means this face has a second wire to bind, not one.

2.  THE STORE IS PASSED EXPLICITLY, NEVER SET GLOBALLY.

    ``nestor.storage`` offers ``set_store()`` as a process-wide global. We do
    not use it. Every call passes ``store=`` so that two modules can never
    share a resolver's store by accident, and so the household's store cannot
    be picked up by code that was not handed it. Nestor's own contract:
    "an explicit argument always wins over the global."

3.  NESTOR IS PINNED TO A TAG OR SHA.

    Never a branch on anything that ships (fleet rule R14). Never vendored:
    vendored source gets read and edited, a wheel in site-packages does not.

═══════════════════════════════════════════════════════════════════════════
VOCABULARY
═══════════════════════════════════════════════════════════════════════════

Nestor's words stop here. This face speaks its own domain and the seam
translates, so the app is never renamed to match a dependency.

    Nestor              this face
    ─────────────       ─────────────────────────────────────────────
    seal                attest / verification   (cf. set_fact_verification)
    canonical           the resolved party, court, creditor, employer
    surface             the form as written in the record
    pair                a verification
    passage             — not used here

═══════════════════════════════════════════════════════════════════════════
FOR AGENTS AND FUTURE READERS
═══════════════════════════════════════════════════════════════════════════

Nestor is a PINNED DEPENDENCY consumed only through this file. Do not modify
it, do not propose changes to it, and do not move logic from this face into
it. If Nestor needs a change, that is an issue on Nestor's own repo.

The subject of work here is *how this face uses Nestor*, never Nestor itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

# Deliberately no `import nestor` yet. Contract first; the import lands with
# the pin and the Storage implementation. See the convention doc.

__all__ = ["bind", "resolver_for", "verify_ledger", "SeamNotBoundError"]


class SeamNotBoundError(RuntimeError):
    """A Nestor call was attempted before `bind()` pinned the ledger.

    Raised rather than defaulted, because the default is the leak: an unbound
    ledger writes household entity resolutions to `data/ledger.jsonl` in the
    working directory. Fail closed — the same posture the promotion gate takes.
    """


_bound: bool = False
_ledger_path: Optional[Path] = None


def bind(household_root: Path) -> None:
    """Pin Nestor's ledger inside the household root. Call once, before use.

    `household_root` is `/.homestead` as resolved by `homestead.keep.paths` —
    never a literal, never a fleet path.
    """
    raise NotImplementedError(
        "bind(): set_ledger_override(household_root / 'keep' / 'ledger.jsonl') "
        "and record _bound. Pending the Nestor pin."
    )


def resolver_for(domain: str, store: Any) -> Any:
    """An `EntityResolver` over an explicitly-injected household store.

    `domain` separates disjoint entity graphs within one store — "party",
    "court", "creditor", "employer" — so a custody matter's people and a
    bankruptcy matter's creditors never cross-talk.

    Must raise `SeamNotBoundError` if `bind()` has not run: constructing a
    resolver with an unpinned ledger is the leak this seam exists to prevent.
    """
    raise NotImplementedError("resolver_for(): pending the Nestor pin.")


def verify_ledger(expected_head: Optional[str] = None) -> bool:
    """Walk the hash chain and confirm every link. Run on read/boot.

    A broken chain is a refusal, not a warning. Note Nestor's own stated limit:
    the walk vouches for every line except the last, which nothing follows —
    pass `expected_head` from somewhere the ledger's writer cannot reach if you
    need the tip covered too.
    """
    raise NotImplementedError("verify_ledger(): pending the Nestor pin.")
