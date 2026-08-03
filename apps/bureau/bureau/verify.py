"""Proof that the building cannot be beaten, and measurement of how much it
looks like it can.

Two searches over the same graph.

**Strict** honours the fine print: a requirement for an attestation *of you* is
not met by an attestation of the room. Verdict: unreachable.

**Credulous** matches on ``kind`` alone — an attestation is an attestation, a
note is a note, a filing is a filing. This is not a weaker checker. It is a
model of the player, and of the Pigeon, both of whom are reading the docket
rather than the fine print. Verdict: reachable.

The gap between those two verdicts is the false-progress arc. It is the thing
the design is actually made of, so it is measured here rather than asserted in
a README: ``prove().false_summits`` is exactly the set of documents you can
hold, that display as the thing Records asked for, and are not it.

Both searches are fixpoints. Document acquisition is monotone — nothing in this
building takes a document away from you — so each closure is unique, order-
independent, and complete over every strategy, including ones nobody has
thought of.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import graph as G


@dataclass(frozen=True)
class Proof:
    obtainable: frozenset[str]
    credulous_obtainable: frozenset[str]
    unissuable: frozenset[str]
    false_summits: frozenset[str]

    @property
    def deadlocked(self) -> bool:
        return G.GOAL not in self.obtainable

    @property
    def looks_winnable(self) -> bool:
        return G.GOAL in self.credulous_obtainable

    def explain(self) -> str:
        def names(s):
            return ", ".join(sorted(s)) or "-"

        return "\n".join(
            [
                f"strictly obtainable:    {names(self.obtainable)}",
                f"credulously obtainable: {names(self.credulous_obtainable)}",
                f"required, never issued: {names(self.unissuable)}",
                f"false summits:          {names(self.false_summits)}",
                f"deadlocked: {self.deadlocked}   looks winnable: {self.looks_winnable}",
            ]
        )


def closure(offices=None, credulous: bool = False) -> frozenset[str]:
    offices = G.OFFICES if offices is None else offices
    held: frozenset[str] = frozenset()
    while True:
        grown = set(held)
        for office in offices.values():
            if office.issues and office.can_serve(held, credulous):
                grown.add(office.issues)
        if grown == set(held):
            return held
        held = frozenset(grown)


def prove(offices=None) -> Proof:
    offices = G.OFFICES if offices is None else offices
    strict = closure(offices, credulous=False)
    credulous = closure(offices, credulous=True)

    demanded: list[G.Req] = []
    for office in offices.values():
        demanded.extend(office.requires)
    issued = {o.issues for o in offices.values() if o.issues}

    unissuable = {
        doc_id
        for doc_id, doc in G.DOCS.items()
        if doc_id not in issued and any(r.met_by(doc_id) for r in demanded)
    }

    # A false summit is obtainable, displays as something Records asked for, and
    # does not actually satisfy it.
    false_summits = {
        doc_id
        for doc_id in strict
        if any(r.met_by(doc_id, credulous=True) and not r.met_by(doc_id) for r in demanded)
    }

    return Proof(
        obtainable=strict,
        credulous_obtainable=credulous,
        unissuable=frozenset(unissuable),
        false_summits=frozenset(false_summits),
    )


def with_mutant_issuers(*doc_ids: str):
    """Install an issuer for each named document. Used to break the graph."""
    mutated = dict(G.OFFICES)
    for i, doc_id in enumerate(doc_ids):
        mutated[f"mutant_{i}"] = G.Office(
            id=f"mutant_{i}",
            name="Office of Things Somebody Saw",
            staff="nobody, because this office does not exist",
            issues=doc_id,
            requires=(G.TICKET,),
            rule="If this office existed the building would be six moves deep.",
        )
    return mutated


def with_mutant_issuer(doc_id: str, office_id: str = "mutant"):
    """The deliberate break — one office that issues the unissuable.

    A gate that cannot fail is not a gate. If installing this does not flip the
    strict verdict, the strict verdict was never measuring anything.
    """
    mutated = dict(G.OFFICES)
    mutated[office_id] = G.Office(
        id=office_id,
        name="Office of Things Somebody Saw",
        staff="nobody, because this office does not exist",
        issues=doc_id,
        requires=(G.TICKET,),
        rule="If this office existed the building would be four moves deep.",
    )
    return mutated


if __name__ == "__main__":  # pragma: no cover
    print(prove().explain())
