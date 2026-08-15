"""Verify the disposition chain — by asking Nestor, not by reimplementing it.

`disposition.Log` writes `prev` on every line with stdlib `hashlib`, because the
four core modules are third-party-free and a test enforces it. Walking that
chain is a different job, and the house already did it: `nestor.ledger.verify()`
is the fleet's hash-chain verifier, and Nestor is the store's sealed answer to
"where do ratified records live" — *only store in the fleet with a seal, a
signature, and a hash chain; a decision recorded anywhere else is asserted, not
ratified.*

So this module imports Nestor and the core does not. That is the direction the
promotion bar requires — **the host imports it, never the reverse** — and it is
why the import lives in a fifth module rather than in `disposition.py`: making
`playgate.audit` unavailable costs you verification, never the ability to run
the gate or write the log.

**Why there is no fallback verifier here.** Writing a stdlib chain-walk would be
twenty lines and would pass its own tests. It would also be the exact tax
`CLAUDE.md` rule 11 names — a mechanism rebuilt because the one that existed was
unfindable at the moment of building — and it would be the *second* place the
chain format is understood, free to drift from the one Nestor tests. Without
Nestor installed this module reports that it cannot verify. An audit tool that
answers "probably fine" when its verifier is missing is worse than one that
answers "I cannot check."

**The last line.** The chain vouches for every entry except the newest, which
nothing follows: edit it and the walk still passes. `expected_head` closes that,
and only if the value was kept where this app cannot reach it. The fleet sealed
this — *hold verify()'s head somewhere the chain's writer cannot reach, and pass
it back as expected_head* — and sealed shut the weaker version, that a
self-documenting marker in the file suffices on its own.
"""
from __future__ import annotations

from pathlib import Path

#: What `verify()` puts in `status`.
OK = "ok"
BROKEN = "broken"
UNVERIFIABLE = "unverifiable"
UNCHAINED = "unchained"


class VerifierUnavailable(RuntimeError):
    """Nestor is not importable, so the chain cannot be checked here."""


def _nestor_verify():
    try:
        from nestor.ledger import verify as _verify
    except ImportError as exc:                      # pragma: no cover - env-dependent
        raise VerifierUnavailable(
            "nestor is not installed, so the disposition chain cannot be "
            "verified. Install the pinned build:\n"
            '  pip install "nestor @ git+https://github.com/rudi193-cmd/Nestor@v0.2.0"'
        ) from exc
    return _verify


def unchained_prefix(path: "str | Path") -> int:
    """How many leading lines predate the chain (carry no ``prev``).

    Non-zero on a log that was written before this app chained anything. It is
    reported rather than repaired: rewriting those lines to carry hashes would
    produce a chain that walks clean over entries nothing ever protected, which
    is a forged provenance, not a migration. The fleet has this one recorded as
    standing law — *rechain() proves the migration and the forgery are the same
    operation* — so the honest move is to name the boundary and leave it.
    """
    p = Path(path)
    if not p.exists():
        return 0
    import json

    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            break
        if "prev" in rec:
            break
        count += 1
    return count


def verify(path: "str | Path", expected_head: "str | None" = None) -> dict:
    """Walk the disposition chain with Nestor's verifier.

    Returns ``{"status": ..., "detail": str, "unchained": int}``. `status` is
    `ok`, `broken`, `unverifiable` (Nestor absent), or `unchained` (the log
    predates the chain entirely, so there is nothing to walk rather than
    something that failed).

    `expected_head` is checked by Nestor and is the only thing that can vouch
    for the newest line. Pass a value that was stored outside this log.
    """
    path = Path(path)
    leading = unchained_prefix(path)
    try:
        nestor_verify = _nestor_verify()
    except VerifierUnavailable as exc:
        return {"status": UNVERIFIABLE, "detail": str(exc), "unchained": leading}

    ok, detail = nestor_verify(str(path), expected_head=expected_head)
    if ok:
        return {"status": OK, "detail": detail, "unchained": leading}

    if leading:
        # Distinguish "this log started before the chain existed" from "someone
        # edited a chained line". Both make the walk fail; only the second is an
        # allegation, and reporting the first as tampering would cry wolf on
        # every log that predates the upgrade.
        return {
            "status": UNCHAINED,
            "detail": (
                f"the first {leading} line(s) predate the chain and carry no "
                f"'prev', so the walk cannot start: {detail}. Those lines were "
                "never protected and cannot be brought under it now — "
                "retro-chaining a log is indistinguishable from forging one. "
                "Entries appended from here are chained; to get a log that "
                "verifies end to end, start a new one and keep this as history."
            ),
            "unchained": leading,
        }
    return {"status": BROKEN, "detail": detail, "unchained": leading}
