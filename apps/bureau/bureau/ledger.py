"""Turn structural findings into predictions Oakenscroll's Office can grade.

The point of the bridge is one distinction, and getting it wrong would quietly
wreck the instrument it feeds.

**A false summit is a theorem, not a prediction.** ``verify.prove`` computes a
fixpoint. That ``attestation_room`` fails ``attestation (presence)`` is not
something that might turn out otherwise; it is arithmetic over the model. Filing
it at 99% would be logging a certainty as a forecast, scoring a free win, and
pulling the reliability diagram toward "well calibrated" using rows that were
never in doubt. A calibration ledger fed proofs stops measuring anything.

So the proofs are **not** what gets logged. What gets logged is the part that
can actually be wrong:

    the model is faithful to the system it claims to describe.

The solver's arithmetic is sound. The modelling is the risk — the office nobody
mentioned, the form that exists but is undocumented, the exception granted by
someone with authority the graph never encoded. That is the input you assumed,
and it is where the failure always is. It is also genuinely uncertain, which is
what makes it a prediction rather than a boast.

Three claim shapes, each with an explicit falsifier:

* **no_issuer** — nobody issues this document. Falsified by finding an issuer.
* **will_be_refused** — this near-miss will be offered and rejected. Falsified
  by it being accepted.
* **model_survives_remodelling** — the unreachable verdict still holds when the
  system is modelled again from primary sources. Falsified by a second pass
  reaching the goal.

Confidence is never auto-assigned. It is the one number the ledger exists to
grade, and inventing it would be fabricating the measurement. ``emit`` refuses
to produce a row without a stated confidence.

This module does not import Oakenscroll's Office. quick-stupids cannot be a
dependency and must not become one in the other direction either; the rows are
plain dicts in that app's ``state_claim`` shape, for it to ingest on its side.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import graph as G
from . import verify

# Mirrors oakenscrolls-office office_db.CONF_MIN/CONF_MAX. Duplicated across a
# repo boundary on purpose (no import), so it can drift. tests/test_ledger.py
# checks it against the real source when a checkout is present and says so
# loudly when it is not.
CONF_MIN, CONF_MAX = 0.5, 0.99

DAY = 86_400


def _a(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


@dataclass(frozen=True)
class Claim:
    """A falsifiable statement awaiting a confidence from a human."""

    key: str
    kind: str
    claim: str
    falsified_by: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    suggested_due_days: int = 90

    def row(self, confidence: float, now: int) -> dict:
        """A row in ``state_claim(claim, confidence, due, tags)`` shape."""
        if confidence is None:
            raise ValueError(
                f"{self.key}: confidence must be stated by a person. "
                "This module will not invent the number the ledger grades."
            )
        if not (CONF_MIN <= confidence <= CONF_MAX):
            raise ValueError(
                f"{self.key}: confidence {confidence} outside [{CONF_MIN}, {CONF_MAX}] "
                "— state the claim in the direction you believe"
            )
        return {
            "claim": self.claim,
            "confidence": float(confidence),
            "due": now + self.suggested_due_days * DAY,
            "tags": tuple(self.tags),
        }


def claims(system: str = "UTETY Office of Records", proof=None) -> list[Claim]:
    """Every falsifiable claim implied by a structural finding.

    Note what is absent: nothing here asserts that the fixpoint is correct.
    That is checked by the suite, not predicted by the ledger.
    """
    proof = verify.prove() if proof is None else proof
    base = ("bureau", "structural", system)
    out: list[Claim] = []

    for doc_id in sorted(proof.unissuable):
        doc = G.DOCS[doc_id]
        out.append(
            Claim(
                key=f"no_issuer:{doc_id}",
                kind="no_issuer",
                claim=(
                    f"In {system}, no office issues {_a(doc.kind)} {doc.kind} qualifying as "
                    f"{'/'.join(sorted(doc.qual))} ({doc.label}). No route to one "
                    f"will be found."
                ),
                falsified_by=f"any office is found that issues {doc_id}",
                tags=base + ("no_issuer",),
            )
        )

    for doc_id in sorted(proof.false_summits):
        doc = G.DOCS[doc_id]
        out.append(
            Claim(
                key=f"will_be_refused:{doc_id}",
                kind="will_be_refused",
                claim=(
                    f"In {system}, {doc.label} will be presented as satisfying "
                    f"{_a(doc.kind)} {doc.kind} requirement and refused on the qualifier."
                ),
                falsified_by=f"{doc_id} is accepted in place of the requirement",
                tags=base + ("false_summit",),
                suggested_due_days=60,
            )
        )

    out.append(
        Claim(
            key="model_survives_remodelling",
            kind="model_survives_remodelling",
            claim=(
                f"The unreachable verdict for {system} still holds when the system "
                f"is modelled again from primary sources by someone who has not "
                f"seen this graph."
            ),
            falsified_by="an independent model reaches the goal",
            tags=base + ("fidelity",),
            suggested_due_days=180,
        )
    )
    return out


def emit(confidences: dict[str, float], now: int, system: str = "UTETY Office of Records",
         proof=None) -> list[dict]:
    """Rows for ``state_claim``. Every claim needs a confidence or this raises.

    ``now`` is passed in rather than read from the clock so the output is
    reproducible and the caller owns the timestamp.
    """
    found = claims(system=system, proof=proof)
    missing = [c.key for c in found if c.key not in confidences]
    if missing:
        raise ValueError(
            "no confidence stated for: " + ", ".join(missing)
            + " — the ledger grades this number; it is not mine to guess"
        )
    return [c.row(confidences[c.key], now) for c in found]


def dry_run(system: str = "UTETY Office of Records") -> str:
    lines = [
        f"{len(claims(system=system))} claims await a confidence.",
        "None of them is the proof. The proof is not a prediction.",
        "",
    ]
    for c in claims(system=system):
        lines += [
            f"  [{c.kind}] {c.key}",
            f"    claim:        {c.claim}",
            f"    falsified by: {c.falsified_by}",
            f"    due:          +{c.suggested_due_days}d      confidence: ?",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(dry_run())
