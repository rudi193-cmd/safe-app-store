#!/usr/bin/env python3
"""A walkthrough of the resolver on synthetic data. `make run app=marching-arts`.

Not a product surface — P1 and P2 ship nothing a user sees. This exists so the
guarantees can be watched happening rather than read about, which is a
different kind of convincing than a passing test suite.

Steps 1–7 are P1's resolver. Steps 8–12 are P2: a minor, a guardian, a refusal
that comes from the database rather than from this file, and an authority that
ends on a birthday with nothing scheduled.

Every person and every record below is invented.
"""
from __future__ import annotations

import datetime
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402
from marching_arts.consent import ConsentedRoster  # noqa: E402
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

    consent_walkthrough()
    print()
    return 0


def consent_walkthrough() -> None:
    """P2, on the same connection: guardians, expiry, and the ledger."""
    roster = ConsentedRoster(Store(":memory:"))
    today = datetime.date.today()

    def on_a_birthday(years_ago: int) -> str:
        return today.replace(year=today.year - years_ago).isoformat()

    roster.register_member("tan", on_a_birthday(17), "2026 registration")
    roster.register_guardian("guardian:tan", "tan", "child", "2026 registration")
    roster.store.record_fact("tan", Band.CRAFT, "rehearsal log 07-14",
                             payload="mellophone 2; horn angle drops in the arc")

    rule("8. A seventeen-year-old. The member cannot consent for themselves.")
    try:
        roster.store.record_grant("tan", "delacroix", Band.CRAFT,
                                  GrantState.SEALED.value, "asked at rehearsal",
                                  sealed_by="tan")
    except sqlite3.IntegrityError as refused:
        print(f"  refused by the database: {refused}")
    print("\n  \033[2mA trigger in migration 002, not a validator in the app. The refusal")
    print("  holds for code paths that have never heard of the rule.\033[0m")

    rule("9. The section leader may not ask for their own access either")
    try:
        roster.request("tan", "delacroix", Band.CRAFT,
                       requested_by="delacroix", source="asked at rehearsal")
    except sqlite3.IntegrityError as refused:
        print(f"  refused by the database: {refused}")
    print("\n  \033[2mAsking is the pressure. A section leader canvassing their own squad")
    print("  is coercion with extra steps, so the beneficiary is not a valid asker.\033[0m")

    rule("10. The guardian seals it")
    roster.seal("tan", "delacroix", Band.CRAFT, "guardian:tan",
                "signed consent form 2026-05-02", requested_by="hayes")
    show(roster.store, Principal("delacroix"), "section leader sees")

    rule("11. The member turns eighteen. Nothing runs.")
    roster.register_member("tan", on_a_birthday(18), "2026 registration")
    show(roster.store, Principal("delacroix"), "section leader sees")
    print("  the grant row is untouched and still says: "
          + roster.connection.execute("SELECT state FROM grants").fetchone()[0])
    print("\n  \033[2mThe resolver stopped honouring guardian authority on a birthday.")
    print("  No scheduled job, so no scheduled job that failed to run.\033[0m")

    rule("12. Somebody opens the roster. Now the member gets asked.")
    reopened = ConsentedRoster(Store(roster.connection))
    print(f"  opening converted: {reopened.opened.converted}")
    print("  the grant row now says: " + ", ".join(
        f"{state} via {via} signed_by={signer}" for state, via, signer in
        reopened.connection.execute("SELECT state, granted_via, sealed_by FROM grants")))
    show(reopened.store, Principal("delacroix"), "section leader sees")
    print("  opening again converts: "
          f"{ConsentedRoster(Store(roster.connection)).opened.converted}")
    print("\n  \033[2mExpiry is a predicate and needs no caller. Conversion is a write,")
    print("  so its caller is opening the file — the same place migrations run.")
    print("  Pending, unsigned, and nobody but the member is told it is waiting.\033[0m")

    rule("13. The ledger is where the history lives")
    for row in roster.disclosures("tan", reader="tan"):
        print(f"  {row['at'][:19]}  {row['action']:<32} {row['detail']}")
    print("\n  \033[2mHash-chained with a count anchor, on this same connection. Editing a")
    print("  row breaks the links; deleting the newest rows breaks the count.\033[0m")

    rule("14. Every step above trusted a string. Now it does not.")
    from marching_arts.auth import AuthError, Authenticator, unproven

    auth = Authenticator(roster.connection, iterations=100_000)
    roster.store.auth = auth
    SECRET = "correct horse battery staple"

    def FAR_FUTURE_PROOF(who: Principal) -> str:
        """The same digest with a later expiry stapled on — the edit the signed
        message exists to refuse."""
        later = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(days=3650)).isoformat()
        return f"{later}.{who.proof.rpartition('.')[2]}"

    print("  before enrolment, an unproven principal resolves: "
          f"count={roster.count(Principal('delacroix'))}")

    auth.enroll("delacroix", SECRET, "roster-import")
    auth.enroll("tan", SECRET, "roster-import")
    print("  credentials enrolled — the database is armed, one way, for good")
    real = auth.authenticate("delacroix", SECRET)
    for label, who in (
        ("fabricated outright", Principal("delacroix")),
        ("someone else's identity", replace(real, person_id="hayes")),
        ("a role added afterwards", replace(real, roles=frozenset({"director"}))),
        ("an expiry pushed out", replace(real, proof=FAR_FUTURE_PROOF(real))),
        ("expired", auth.authenticate("delacroix", SECRET, ttl_seconds=-1)),
        ("the proof stripped off", unproven(real)),
    ):
        try:
            roster.count(who)
            print(f"    {label:<26} LEAKED")
        except AuthError as refusal:
            print(f"    {label:<26} refused — {refusal}")

    show(roster.store, auth.authenticate("tan", SECRET),
         "tan, proven, sees own record")
    print("\n  \033[2mThe check is inside predicate(), which every read already went")
    print("  through — so count, visible and subjects are all gated by one line and")
    print("  a fourth read added later inherits it. The signing key is per-process")
    print("  and never written down, so there is no key in the file to steal.")
    print("  What this does NOT do: the file is still fully readable by anyone")
    print("  holding it. This gates the resolver, not the disk.\033[0m")


if __name__ == "__main__":
    raise SystemExit(main())
