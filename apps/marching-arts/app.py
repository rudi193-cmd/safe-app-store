#!/usr/bin/env python3
"""A walkthrough of the resolver on synthetic data. `make run app=marching-arts`.

Not a product surface — P1 ships nothing a user sees. This exists so the
guarantees can be watched happening rather than read about, which is a
different kind of convincing than a passing test suite.

Every person and every record below is invented.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402
from marching_arts.rules import compile_rules, explain  # noqa: E402


def rule(text: str) -> None:
    print(f"\n\033[1m{text}\033[0m\n" + "─" * 62)


def show(store: Store, who: Principal, label: str) -> None:
    rows = store.visible(who)
    print(f"  {label:<28} count={store.count(who)}  subjects={store.subjects(who)}")
    for r in rows:
        payload = r.payload if r.payload is not None else "\033[2m(withheld)\033[0m"
        detail = f"    L{r.band} {payload}"
        if r.instruction:
            detail += f"  →  {r.instruction}"
        print(detail)


def main() -> int:
    store = Store(":memory:")

    # A squad: two members and the section leader over them. The leader is also
    # a member, with their own record, which is the case that breaks per-user
    # authorization models.
    store.record_fact("rivera", Band.ROSTER, "2026 registration",
                      payload="snare 3")
    store.record_fact("rivera", Band.CRAFT, "rehearsal log 07-14",
                      payload="left-hand height inconsistent above 140bpm")
    store.record_fact("rivera", Band.HEALTH, "medical form on file",
                      payload="exercise-induced asthma",
                      instruction="water break every twenty minutes in heat")
    store.record_fact("okonkwo", Band.CRAFT, "rehearsal log 07-14",
                      payload="clean; move to the front of the block")
    store.record_fact("delacroix", Band.ROSTER, "2026 registration",
                      payload="section leader, snare")

    rule("1. Nobody has consented yet")
    print("  Three members on the roster. The section leader holds no grants.")
    show(store, Principal("delacroix"), "section leader sees")
    print("\n  \033[2mNot an empty list with three greyed rows — an empty list.")
    print("  A slot where a refusal would render is itself a disclosure.\033[0m")

    rule("2. One member's guardian seals a craft-band grant")
    store.record_grant("rivera", "delacroix", Band.CRAFT,
                       GrantState.SEALED.value, "signed consent form 2026-05-02",
                       sealed_by="guardian:rivera")
    show(store, Principal("delacroix"), "section leader sees")
    print("\n  \033[2mThe health record exists and is not shown: the grant reaches L2,")
    print("  the record sits at L4. A grant covers its band and everything below.\033[0m")

    rule("3. The system infers a second grant. It does not take effect.")
    store.record_grant("okonkwo", "delacroix", Band.CRAFT,
                       GrantState.DRAFT.value, "inferred from section assignment")
    show(store, Principal("delacroix"), "section leader sees")
    print("\n  \033[2mDraft. A machine produced it, so it is recorded and inert.")
    print("  Only a human seals — and from outside, draft and never-asked look alike.\033[0m")

    rule("4. The grant is widened to cover health")
    store.record_grant("rivera", "delacroix", Band.HEALTH,
                       GrantState.SEALED.value, "signed consent form 2026-06-11",
                       sealed_by="guardian:rivera")
    show(store, Principal("delacroix"), "section leader sees")
    print("\n  \033[2mDerive the instruction, do not forward the fact. The leader learns")
    print("  what to do. The diagnosis never left the database.\033[0m")

    rule("5. The member sees their own record in full")
    show(store, Principal("rivera"), "rivera sees")

    rule("6. Consent is withdrawn")
    store.revoke("rivera", "delacroix")
    show(store, Principal("delacroix"), "section leader sees")
    print("\n  \033[2mImmediate, and silent. Nothing notifies the grantee, and no residue")
    print("  of the former grant is readable — the ledger is where history lives.\033[0m")

    rule("7. Roles are not authority")
    director = Principal("hayes", roles=frozenset({"director", "caption_head"}))
    show(store, director, "director sees")
    predicate, params = compile_rules(store.policy.rules(director))
    print(f"\n  predicate: {predicate[:58]}…")
    for reason in explain(store.policy.rules(director)):
        print(f"    {reason}")
    print("\n  \033[2mEvery role in the program, and no grant naming them. L4 is named")
    print("  persons only — not caption heads, not program coordinators.\033[0m")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
