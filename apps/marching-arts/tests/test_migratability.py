"""What has to hold before a corps can put a real season in this file.

Every other test module in this app runs against a fresh ``:memory:`` store with
a handful of rows, which is the right shape for asking whether the predicate is
correct and the wrong shape for asking whether the *artifact* is usable. Four
things separate the two, and none of them had a test:

1. **Forward migration on populated data.** Every existing test builds its
   schema and its rows in the same breath, so migration 005 has only ever run
   against an empty database. A corps that used this last season has one that
   isn't.
2. **Scale.** 150 members and a season of facts. The resolver's authorization
   clause is a *correlated* subquery with a second correlated subquery nested
   inside it, and correlated means per-row — so the thing to check is not only
   the clock but the query plan, because a lost index turns per-row lookups into
   per-row scans and the arithmetic stops being linear.
3. **Concurrent access.** Two connections, one file. The consent chain allocates
   its own ``seq`` with a read-then-insert, which is a race; what makes it safe
   is SQLite's write lock and the chain's primary key, and neither had ever been
   made to fire.
4. **Backup and restore.** The whole argument for keeping consent, disclosure
   and domain data on one connection is that they are restored as a unit. That
   argument is only as good as the mechanism that catches a restore which
   *wasn't*.

These tests are deliberately slower and heavier than the rest of the suite. They
use real files rather than ``:memory:`` wherever the thing under test is a
property of the file — a backup of an in-memory database proves nothing about a
backup, and two connections to ``:memory:`` are two databases.

**What this module structurally cannot see.** It runs one SQLite build in one
process tree on one filesystem. It says nothing about a network filesystem
(where SQLite's locking is unreliable), nothing about WAL mode (the app does not
set it, and a host that does gets different concurrency), and nothing about a
crash *between* two statements — only about a lock contended between them.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from marching_arts import Store  # noqa: E402
from marching_arts import schema  # noqa: E402
from marching_arts.bands import Band  # noqa: E402
from marching_arts.consent import (  # noqa: E402
    ChainTamperError,
    ConsentedRoster,
    consent_chain,
)
from marching_arts.policy import Principal  # noqa: E402

#: The migration names, in order, frozen as a literal. Not derived from
#: ``schema.MIGRATIONS`` — deriving it would make the test agree with whatever
#: the module currently says, which is the one thing it must not do. See
#: ``test_no_migration_is_renumbered_or_inserted_ahead_of_an_applied_one``.
APPLIED_ORDER = (
    "001_facts_and_grants",
    "002_people_guardianship_and_consent_chain",
    "003_minor_use_consent_is_a_guardians_to_give",
    "004_consent_chain_is_per_subject",
    "005_rationale",
    "006_credentials_and_the_arming_latch",
)

#: The stored chain name for subject ``kid``, as a literal — ``sha256("kid")``
#: truncated to 32 hex characters, which is what ``consent.consent_chain``
#: computes. Written out rather than computed for the same reason
#: ``APPLIED_ORDER`` is: a name that exists in files on other people's disks is
#: part of the format, and a test that recomputes it agrees with any rename.
#:
#: Mutation-checked. Shortening the truncation to 31 characters is invisible to
#: every other assertion in this module, because the fixture writes the chain
#: with the same function the test reads it with — a self-consistent rename that
#: passes cleanly here and orphans every chain already on disk.
KID_CHAIN = "consent/5c77d7fd8f51ed0c2a913e46326ff6d2"


def _iso(years_ago: int) -> str:
    """A birthdate that is exactly ``years_ago`` years old today.

    Computed from today rather than hardcoded, because a fixture with a literal
    birthdate stops describing a minor at some point after it is written and the
    test then passes for the wrong reason.
    """
    today = datetime.date.today()
    try:
        return today.replace(year=today.year - years_ago).isoformat()
    except ValueError:            # 29 February
        return today.replace(year=today.year - years_ago, day=28).isoformat()


# ══ 1 ═══ forward migration on a populated database ═══════════════════════════
#
# The upgrade path is the one code path a corps runs that this project never
# runs itself, because every test and every demo starts from nothing. It is also
# the one where a mistake is unrecoverable: a bad migration against real rows
# does not fail a test, it eats a season.


@pytest.fixture()
def older_install(tmp_path):
    """A database written by a build that only knew migrations 001–004.

    ``schema.MIGRATIONS`` is truncated while the file is *written*, which is the
    only way to get an older schema out of a repo that has only ever had the
    current one, and restored **before the test runs** — the test is the upgrade,
    so it needs the full list. Getting that order wrong is not a failing fixture,
    it is a fixture that hands every test below a database which is never
    upgraded and assertions that then pass or fail for reasons unrelated to what
    they are named after; it cost three failures on the first run of this module.
    """
    full = schema.MIGRATIONS
    path = str(tmp_path / "last-season.db")
    try:
        schema.MIGRATIONS = full[:4]
        roster = ConsentedRoster(Store(path))
        roster.register_member("kid", _iso(16), "roster-import-2025")
        roster.register_guardian("parent", "kid", "child", "guardian-form-2025")
        roster.seal("kid", "leader", int(Band.CRAFT), "parent", "guardian-form-2025")
        roster.grant_use("kid", "local_only", "parent")
        roster.store.record_fact(
            "kid", int(Band.CRAFT), "rehearsal-2025-06-14", payload="watch the dot")
        roster.connection.commit()
        roster.connection.close()
    finally:
        schema.MIGRATIONS = full
    yield path
    assert schema.MIGRATIONS is full, "a leaked truncation would disable 005 app-wide"


def _applied(conn) -> "list[str]":
    return [r[0] for r in conn.execute(
        "SELECT name FROM schema_migrations ORDER BY name")]


def test_the_older_install_really_is_older(older_install):
    """Guards the fixture, not the app. A fixture that quietly built the current
    schema would make every test below pass while testing nothing, which is the
    stale-reference failure this project has already shipped once."""
    conn = sqlite3.connect(older_install)
    assert _applied(conn) == list(APPLIED_ORDER[:4])
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='rationale'"
    ).fetchone()[0] == 0


def test_an_older_install_upgrades_without_losing_a_row(older_install):
    """The upgrade itself. Migration 002 rebuilds ``grants`` by rename-copy-drop,
    so 'the migrations are additive' is false and the copy has to be checked."""
    before = sqlite3.connect(older_install)
    facts = before.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    grants = before.execute(
        "SELECT subject_id, grantee_id, band, state, sealed_by, granted_via"
        " FROM grants ORDER BY id").fetchall()
    chain = before.execute("SELECT COUNT(*) FROM consent_chain").fetchone()[0]
    before.close()
    assert facts == 1 and chain > 0 and len(grants) == 1

    upgraded = Store(older_install)                    # runs 005
    assert _applied(upgraded.connection) == list(APPLIED_ORDER)
    assert upgraded.connection.execute(
        "SELECT COUNT(*) FROM facts").fetchone()[0] == facts
    assert upgraded.connection.execute(
        "SELECT subject_id, grantee_id, band, state, sealed_by, granted_via"
        " FROM grants ORDER BY id").fetchall() == grants
    assert upgraded.connection.execute(
        "SELECT COUNT(*) FROM consent_chain").fetchone()[0] == chain


def test_the_predicate_still_resolves_last_seasons_rows(older_install):
    """Data surviving the upgrade is not enough — it has to still *authorize*.
    A guardian-sealed grant written under 002's triggers must still be honoured
    by the resolver after 005, and the member must still see their own row."""
    store = Store(older_install)
    assert [f.payload for f in store.visible(Principal("leader"))] == ["watch the dot"]
    assert store.count(Principal("kid")) == 1


def test_the_consent_chain_verifies_after_an_upgrade(older_install):
    """The chain is hashed over its rows' JSON. Any migration that reformatted a
    stored row — or renamed a chain, as 004 did to the *naming scheme* — would
    break every link at once, and the failure would surface as a member's
    consent silently reading as denied."""
    roster = ConsentedRoster(Store(older_install))
    roster.verify()                                    # every subject, not just one
    roster.verify("kid")
    assert roster.permitted("kid", "local_only") is True


def test_the_stored_chain_name_is_the_one_last_seasons_file_already_uses(older_install):
    """The chain name is part of the on-disk format, so it is pinned to a literal.

    Every other assertion in this module is blind to a rename: the fixture writes
    the chain through ``consent_chain`` and the test reads it through
    ``consent_chain``, so shortening the subject hash by one character is
    perfectly self-consistent and perfectly invisible — while orphaning the
    chains in every file a corps already has. The same shape as a renumbered
    migration, and closed the same way.
    """
    assert consent_chain("kid") == KID_CHAIN
    conn = sqlite3.connect(older_install)
    assert conn.execute(
        "SELECT count FROM consent_anchor WHERE chain = ?", (KID_CHAIN,)
    ).fetchone() == (1,)
    assert conn.execute(
        "SELECT COUNT(*) FROM consent_chain WHERE chain = ?", (KID_CHAIN,)
    ).fetchone()[0] == 1
    conn.close()


def test_the_new_table_is_usable_on_an_upgraded_database(older_install):
    """005's gate has to hold on a database that predates it, not only on one
    created with it — the triggers are created by the migration and a migration
    that ran its DDL but not its triggers would leave the table wide open."""
    store = Store(older_install)
    store.record_rationale(
        "why-no-health", "Why can I not see that?", "Because L4 is named persons only.",
        "docs/BUILD_PLAN.md", mechanism="policy.Policy.projection, DERIVE_AT")
    assert store.rationale() == []                     # draft does not ship
    with pytest.raises(sqlite3.IntegrityError):
        store.record_rationale("no-mech", "q?", "a", "src",
                               publication="shipped", sealed_by="sean")


def test_upgrading_twice_runs_nothing_the_second_time(older_install):
    """Idempotence, from the outside. ``apply`` returns the names it ran, and on
    a database already at head that list must be empty — an upgrade that re-ran
    002 would rename ``grants`` a second time and copy an empty table over it."""
    assert schema.apply(sqlite3.connect(older_install)) == list(APPLIED_ORDER[4:])
    assert schema.apply(sqlite3.connect(older_install)) == []
    assert schema.apply(sqlite3.connect(older_install)) == []


def test_no_migration_is_renumbered_or_inserted_ahead_of_an_applied_one():
    """The ledger is keyed by name, so a name is permanent.

    Rename ``003`` and every install that already ran it runs it again. Insert a
    new migration between 002 and 003 and it never runs at all on an existing
    install, because ``apply`` skips by membership and not by position — the new
    file would be applied on fresh databases and silently absent on real ones,
    which is the worst of the available outcomes and produces two schemas that
    both report themselves up to date.

    So this list is frozen as a literal and appended to, never edited. If this
    test fails, the fix is a new migration at the end.
    """
    assert tuple(name for name, _ in schema.MIGRATIONS) == APPLIED_ORDER


def test_a_database_from_a_newer_build_is_left_intact_and_not_downgraded(older_install):
    """The reverse direction, recorded rather than defended.

    Older code opening a *newer* database applies nothing and proceeds against a
    schema it does not know. That is the survivable half — it does not drop the
    unknown migration's tables and does not rewrite its rows — and it is a real
    asymmetry: there is no version ceiling, so an old build will happily read a
    file whose invariants it has never heard of. Named here so the gap is visible
    rather than assumed away, in the same spirit as migration 004's note about
    the partition check it cannot make a trigger.
    """
    conn = sqlite3.connect(older_install)
    conn.execute("INSERT INTO schema_migrations(name) VALUES ('006_from_the_future')")
    conn.execute("CREATE TABLE from_the_future (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    store = Store(older_install)                       # only knows up to 005
    assert "006_from_the_future" in _applied(store.connection)
    assert store.connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='from_the_future'"
    ).fetchone()[0] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1


# ══ 2 ═══ scale: 150 members and a season ═════════════════════════════════════
#
# A World Class corps is 150 members. `SEASON_FACTS` per member is a season's
# worth of rehearsal notes at the granularity this app stores them.

MEMBERS = 150
SEASON_FACTS = 24
SQUAD = 13                       # 12 sections of 13, which is 150 rounded up

#: Bands 0–6 cycling over 24 facts: bands 0,1,2 land four times each and bands
#: 3,4,5,6 land three times each. The arithmetic below depends on that split, so
#: it is stated once here rather than recomputed in four places.
_PER_MEMBER_LOW = 4 * 3          # bands 0,1,2 — under a CRAFT grant
_PER_MEMBER_SERVED = SEASON_FACTS - 3       # everything except the three at L5


@pytest.fixture(scope="module")
def season():
    """One corps, one season, built once for the whole module.

    A fifth of the roster are minors with a registered guardian and a
    guardian-derived seal, because that is what puts the *nested* correlated
    subquery — ``still_a_minor`` inside the grant lookup — on the hot path. A
    roster of adults would exercise the cheap half and prove nothing.
    """
    store = Store(":memory:")
    conn = store.connection
    for i in range(MEMBERS):
        member = f"m{i:03d}"
        if i % 5 == 0:
            conn.execute(
                "INSERT INTO people(person_id, birthdate, source) VALUES (?,?,?)",
                (member, _iso(16), "roster-import"))
            conn.execute(
                "INSERT INTO guardianships(guardian_id, subject_id, relation, source)"
                " VALUES (?,?,?,?)", (f"g{i:03d}", member, "child", "guardian-form"))
        for k in range(SEASON_FACTS):
            conn.execute(
                "INSERT INTO facts(subject_id, band, payload, instruction, source)"
                " VALUES (?,?,?,?,?)",
                (member, k % 7, f"note-{k}", f"do-{k}", "rehearsal-log"))

    for i in range(MEMBERS):
        member, leader = f"m{i:03d}", f"m{(i // SQUAD) * SQUAD:03d}"
        signer, via = ((f"g{i:03d}", "guardian") if i % 5 == 0 else (member, "member"))
        if member != leader:                  # a leader is not a grantee on themselves
            conn.execute(
                "INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by,"
                " granted_via, source) VALUES (?,?,?,?,?,?,?)",
                (member, leader, int(Band.CRAFT), "sealed", signer, via, "consent-form"))
        conn.execute(
            "INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by,"
            " granted_via, source) VALUES (?,?,?,?,?,?,?)",
            (member, "director", int(Band.FAMILY), "sealed", signer, via, "consent-form"))
    conn.commit()
    return store


def test_the_season_is_the_size_it_claims_to_be(season):
    """Guards the fixture. A leak test over five rows is not a leak test, so the
    volume itself is an assertion."""
    conn = season.connection
    assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == MEMBERS * SEASON_FACTS
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == MEMBERS // 5
    # one director grant per member, plus a leader grant for everyone but the
    # twelve leaders themselves
    leaders = len(range(0, MEMBERS, SQUAD))
    assert conn.execute("SELECT COUNT(*) FROM grants").fetchone()[0] == 2 * MEMBERS - leaders


def test_a_section_leader_sees_their_squad_and_nobody_elses_at_scale(season):
    """The leak the whole app exists to prevent, at a volume where an off-by-one
    in the correlated subquery would be invisible in a five-row fixture.

    Expected, derived rather than observed: the leader's own 21 servable rows
    (24 minus the three at L5, which are refused to everyone including the
    subject) plus 12 squadmates × 12 rows at bands 0–2, the reach of a CRAFT
    grant. 21 + 144 = 165.
    """
    expected = _PER_MEMBER_SERVED + (SQUAD - 1) * _PER_MEMBER_LOW
    assert expected == 165
    leader = Principal("m000")
    rows = season.visible(leader)
    assert len(rows) == expected
    assert season.count(leader) == expected
    assert {r.subject_id for r in rows} == {f"m{i:03d}" for i in range(SQUAD)}
    assert max(r.band for r in rows if r.subject_id != "m000") == int(Band.CRAFT)


def test_count_never_disagrees_with_visible_across_the_whole_roster(season):
    """``count`` is a SQL ``COUNT(*)`` and ``visible`` is a SELECT, so they are
    two predicates that have to stay identical. Checked for all 150 principals
    rather than one, because the shapes that break them apart — a minor, a
    leader who is also a subject, a member with no grants — are a minority of
    the roster and a single-principal test picks the majority by luck."""
    for i in range(MEMBERS):
        who = Principal(f"m{i:03d}")
        assert season.count(who) == len(season.visible(who)), who.person_id


def test_paging_the_roster_yields_every_visible_row_exactly_once(season):
    """Page boundaries are where a filter-in-Python implementation shows itself:
    ``LIMIT`` applied before the predicate returns short pages and drops rows.
    Walked in pages of 50 over 165 rows so the last page is partial."""
    director = Principal("director")
    unpaged = [f.id for f in season.visible(director)]
    paged, offset = [], 0
    while True:
        page = season.visible(director, limit=50, offset=offset)
        if not page:
            break
        paged.extend(f.id for f in page)
        offset += 50
    assert len(paged) == len(set(paged))
    assert paged == unpaged


def test_the_derive_projection_holds_for_every_row_at_scale(season):
    """A band-6 grant over the whole roster is the most access this app can
    express, and it still must not carry a single L4 payload out. Checked over
    every row rather than a sample: the projection is a CASE in the SELECT list,
    and a CASE that is wrong for one band is wrong for a twelfth of the file."""
    rows = season.visible(Principal("director"))
    assert len(rows) == MEMBERS * _PER_MEMBER_SERVED
    assert not any(r.band == int(Band.SAFEGUARDING) for r in rows)
    withheld = [r for r in rows if r.band >= int(Band.ACCOMMODATION)]
    assert withheld and all(r.payload is None for r in withheld)
    assert all(r.instruction is not None for r in withheld)
    assert all(r.payload is not None for r in rows
               if r.band < int(Band.ACCOMMODATION))


def test_subjects_lists_the_squad_and_not_the_corps(season):
    """The empty-state leak at scale. 150 subjects exist; a section leader must
    be able to enumerate 13."""
    assert len(season.subjects(Principal("m000"))) == SQUAD
    assert len(season.subjects(Principal("director"))) == MEMBERS
    assert season.subjects(Principal("nobody")) == []


def test_the_authorization_predicate_never_scans_grants_or_people(season):
    """The cost gate, and the reason it is a plan assertion rather than a clock.

    Both lookups inside the predicate are *correlated*: they run once per
    candidate fact. While each is an index seek the read is linear in the facts
    examined; the moment one becomes a table scan the read is facts × grants,
    and at a season's volume that is 3,600 × 288 rather than 3,600. A timing
    test would catch that on this machine and not on a faster one.

    Deliberately asserts the *absence of a scan* and not the presence of a named
    index — the planner currently satisfies the grant lookup from the autoindex
    behind ``UNIQUE (subject_id, grantee_id)`` rather than from
    ``ix_grants_lookup``, so pinning the name would assert something that is
    already not true.
    """
    predicate, params = season.predicate(Principal("m000"))
    plan = season.connection.execute(
        f"EXPLAIN QUERY PLAN SELECT COUNT(*) FROM facts WHERE {predicate}", params
    ).fetchall()
    steps = " | ".join(row[3] for row in plan)
    assert "SEARCH g USING" in steps, steps
    assert "SEARCH p USING" in steps, steps
    assert "SCAN g" not in steps, steps
    assert "SCAN p" not in steps, steps


def test_a_full_roster_read_is_not_pathologically_slow(season):
    """A smoke ceiling, and honest about being one.

    Twelve section leaders and the director each reading their whole visible set
    is the heaviest thing a host does on this database. It takes tens of
    milliseconds; the ceiling is two seconds, which is loose enough to survive a
    slow shared CI runner and tight enough to fail if a read goes quadratic.

    What it cannot see: anything sublinear-to-quadratic that still fits under the
    ceiling at this volume. That is what the plan assertion above is for, and
    this test is the backstop for a regression the plan assertion has no shape
    for — an N+1 introduced in Python rather than in SQL.
    """
    started = time.perf_counter()
    for i in range(0, MEMBERS, SQUAD):
        who = Principal(f"m{i:03d}")
        season.count(who)
        season.visible(who)
    season.visible(Principal("director"))
    assert time.perf_counter() - started < 2.0


# ══ 3 ═══ concurrent access: two connections, one file ════════════════════════
#
# The app is local-first with no server, which does not mean single-process: a
# corps laptop runs the app while a second window runs an import, and the
# browser half runs a SharedWorker precisely because two writers to one store
# is the expected case rather than the exotic one.
#
# Every test here uses a short `timeout` on the contending connection. SQLite's
# default is five seconds of retry, which turns a lock into a delay and would
# make these tests measure the timeout instead of the behaviour.

CONTENDED_TIMEOUT = 0.2


def _child(path: str, body: str) -> subprocess.CompletedProcess:
    """Run ``body`` in a separate interpreter against the same database file.

    A real second process, not a second connection: process-level locking is the
    thing being tested, and two connections in one interpreter share a
    filesystem view that a second process does not.
    """
    return subprocess.run(
        [sys.executable, "-c",
         "import sys, sqlite3\n"
         f"sys.path.insert(0, {str(APP)!r})\n"
         f"DB = {path!r}\n"
         f"TIMEOUT = {CONTENDED_TIMEOUT!r}\n" + body],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(APP)},
    )


@pytest.fixture()
def shared_file(tmp_path):
    """A real database file with one member on the roster."""
    path = str(tmp_path / "corps.db")
    roster = ConsentedRoster(Store(path))
    roster.register_member("adult", _iso(22), "roster-import")
    roster.grant_use("adult", "local_only", "adult")
    roster.connection.commit()
    roster.connection.close()
    return path


def test_two_processes_both_land_their_facts(shared_file):
    """The base case, and the one that has to work: sequential contention is
    resolved by SQLite's own retry, so neither writer loses a row."""
    children = [
        _child(shared_file,
               "from marching_arts import Store\n"
               "s = Store(DB)\n"
               f"for k in range({n}, {n} + 10):\n"
               "    s.record_fact('adult', 2, 'rehearsal-log', payload=str(k))\n")
        for n in (0, 100)
    ]
    for done in children:
        assert done.returncode == 0, done.stderr
    conn = sqlite3.connect(shared_file)
    assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 20
    assert conn.execute("SELECT COUNT(DISTINCT payload) FROM facts").fetchone()[0] == 20


def test_a_second_writer_is_refused_rather_than_losing_its_write(shared_file):
    """Fail closed on contention. A held write transaction must make the second
    writer *raise*, because the alternative a caller cannot detect is a write
    that returned successfully and is not in the file."""
    holder = sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute(
        "INSERT INTO facts(subject_id, band, source) VALUES ('adult', 1, 'held')")
    try:
        done = _child(shared_file,
                      "from marching_arts import Store\n"
                      "s = Store(sqlite3.connect(DB, timeout=TIMEOUT))\n"
                      "s.record_fact('adult', 2, 'contending', payload='lost?')\n")
        assert done.returncode != 0
        assert "database is locked" in done.stderr
    finally:
        holder.rollback()
        holder.close()
    conn = sqlite3.connect(shared_file)
    assert conn.execute(
        "SELECT COUNT(*) FROM facts WHERE payload = 'lost?'").fetchone()[0] == 0


def test_an_uncommitted_write_is_invisible_to_the_other_process(shared_file):
    """Isolation, stated as a property the resolver depends on. A grant that is
    open in another transaction must not authorize anything yet — a predicate
    that could see uncommitted grants would honour consent that was never given
    if the writing transaction later rolled back."""
    holder = sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute(
        "INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by,"
        " granted_via, source) VALUES"
        " ('adult', 'snoop', 4, 'sealed', 'adult', 'member', 'uncommitted')")
    holder.execute(
        "INSERT INTO facts(subject_id, band, source) VALUES ('adult', 4, 'held')")
    try:
        done = _child(shared_file,
                      "from marching_arts import Store\n"
                      "from marching_arts.policy import Principal\n"
                      "s = Store(sqlite3.connect(DB, timeout=TIMEOUT))\n"
                      "print(s.count(Principal('snoop')))\n")
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == "0"
    finally:
        holder.rollback()
        holder.close()


def test_the_consent_chain_refuses_a_concurrent_append_and_stays_verifiable(shared_file):
    """The race in ``append_row``, made to fire.

    ``seq`` is allocated by ``SELECT MAX(seq) + 1`` and then inserted, which is
    read-then-write and therefore a race. Two things make it safe and neither
    was tested: SQLite serialises writers, and ``PRIMARY KEY (chain, seq)``
    refuses a duplicate if they ever were not serialised. Either way the second
    append must raise — the outcome this test refuses is a chain that silently
    grew a fork, because a forked chain fails verification forever afterwards
    and the consent it records reads as denied.
    """
    first = ConsentedRoster(Store(sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)))
    second = ConsentedRoster(Store(sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)))

    first.connection.execute("BEGIN IMMEDIATE")
    first.connection.execute(
        "INSERT INTO facts(subject_id, band, source) VALUES ('adult', 1, 'held')")
    with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
        second.grant_use("adult", "process_analysis", "adult")
    first.connection.rollback()

    first.verify("adult")
    assert first.permitted("adult", "local_only") is True
    assert first.permitted("adult", "process_analysis") is False
    chain = shared_file and consent_chain("adult")
    assert [r[0] for r in first.connection.execute(
        "SELECT seq FROM consent_chain WHERE chain = ? ORDER BY seq", (chain,))] == [1]
    assert first.connection.execute(
        "SELECT count FROM consent_anchor WHERE chain = ?", (chain,)).fetchone()[0] == 1


def test_a_contended_open_reports_the_member_it_could_not_convert(shared_file):
    """The majority sweep under a real lock, which is what it was written for.

    Opening a roster converts guardian grants whose subject has since turned
    eighteen, and that is a *write*. ``MajoritySweep.unconvertible`` exists so a
    conversion that could not run is reported rather than dropped — and until
    now the only thing that had ever made it non-empty was a synthetic
    exception. A locked database is the real cause, and this is the test that
    the roster still opens, still grants nothing, and still says who was missed.
    """
    roster = ConsentedRoster(Store(shared_file))
    roster.register_member("kid", _iso(16), "roster-import")
    roster.register_guardian("parent", "kid", "child", "guardian-form")
    roster.seal("kid", "leader", int(Band.CRAFT), "parent", "guardian-form")
    # the birthday that happened while the laptop was shut
    roster.connection.execute(
        "UPDATE people SET birthdate = ? WHERE person_id = 'kid'", (_iso(19),))
    roster.connection.commit()
    roster.connection.close()

    holder = sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute(
        "INSERT INTO facts(subject_id, band, source) VALUES ('kid', 1, 'held')")
    try:
        contended = ConsentedRoster(
            Store(sqlite3.connect(shared_file, timeout=CONTENDED_TIMEOUT)))
        assert contended.opened.converted == {}
        assert contended.opened.unconvertible == ("kid",)
        assert bool(contended.opened) is True
        # untouched is the safe state: the guardian seal is still on file and
        # still resolves to nothing, because the subject is no longer a minor
        assert contended.count(Principal("leader")) == 0
    finally:
        holder.rollback()
        holder.close()

    reopened = ConsentedRoster(Store(shared_file))
    assert reopened.opened.converted == {"kid": ["leader"]}
    assert reopened.opened.unconvertible == ()


# ══ 4 ═══ backup and restore ══════════════════════════════════════════════════
#
# The reason grants, chains and roster share one connection is that they are
# restored as a unit or not at all. That is an argument about a mechanism, so
# these tests are about the mechanism: what a whole-file restore preserves, and
# what a partial one is caught by.


@pytest.fixture()
def midseason(tmp_path):
    """A populated file, plus a backup of it, plus writes made afterwards."""
    live = str(tmp_path / "corps.db")
    roster = ConsentedRoster(Store(live))
    roster.register_member("kid", _iso(16), "roster-import")
    roster.register_guardian("parent", "kid", "child", "guardian-form")
    roster.seal("kid", "leader", int(Band.CRAFT), "parent", "guardian-form")
    roster.grant_use("kid", "local_only", "parent")
    roster.store.record_fact("kid", int(Band.CRAFT), "rehearsal-log", payload="june")
    roster.store.record_rationale(
        "why-no-health", "Why can I not see that?", "L4 is named persons only.",
        "docs/BUILD_PLAN.md", mechanism="policy.Policy.projection",
        publication="shipped", sealed_by="sean")

    backup = str(tmp_path / "corps-backup.db")
    with sqlite3.connect(backup) as target:
        roster.connection.backup(target)               # stdlib online backup

    # the season continues after the backup was taken
    roster.grant_use("kid", "process_analysis", "parent")
    roster.store.record_fact("kid", int(Band.CRAFT), "rehearsal-log", payload="july")
    roster.connection.commit()
    roster.connection.close()
    return live, backup


def test_a_restore_carries_every_migration_and_every_row(midseason):
    """The whole file, not the tables somebody remembered to name. A backup that
    restored ``facts`` and not ``schema_migrations`` would produce a database
    that re-ran every migration against populated data."""
    _, backup = midseason
    conn = sqlite3.connect(backup)
    assert _applied(conn) == list(APPLIED_ORDER)
    assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM grants").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM guardianships").fetchone()[0] == 1
    conn.close()


def test_the_restored_copy_resolves_and_its_chain_verifies(midseason):
    """A restore is only a restore if the thing that comes back authorizes the
    same reads and can still prove its own consent history."""
    _, backup = midseason
    restored = ConsentedRoster(Store(backup))
    restored.verify()
    assert restored.permitted("kid", "local_only") is True
    assert [f.payload for f in restored.visible(Principal("leader"))] == ["june"]
    assert [r.topic for r in restored.store.rationale()] == ["why-no-health"]


def test_a_backup_is_a_consistent_earlier_state_not_a_truncated_one(midseason):
    """The distinction the count anchor exists to make.

    The live file has two consent transitions and two facts; the backup has one
    of each. A chain that is *shorter because it was captured earlier* has an
    anchor that agrees with it and verifies. A chain that is shorter because
    somebody deleted the newest rows has an anchor that does not, and the next
    test is that one. Restoring a consistent earlier state must not look like
    tampering — if it did, every restore from backup would read as an attack and
    the mechanism would be useless.
    """
    live, backup = midseason
    live_conn, backup_conn = sqlite3.connect(live), sqlite3.connect(backup)
    chain = consent_chain("kid")
    assert live_conn.execute(
        "SELECT count FROM consent_anchor WHERE chain = ?", (chain,)).fetchone()[0] == 2
    assert backup_conn.execute(
        "SELECT count FROM consent_anchor WHERE chain = ?", (chain,)).fetchone()[0] == 1
    live_conn.close()
    backup_conn.close()

    ConsentedRoster(Store(backup)).verify()            # earlier, and sound
    assert ConsentedRoster(Store(live)).permitted("kid", "process_analysis") is True
    assert ConsentedRoster(Store(backup)).permitted("kid", "process_analysis") is False


def test_a_chain_restored_out_of_step_with_its_anchor_is_detected(midseason):
    """The partial restore, which is the failure a one-file backup prevents and
    a table-by-table one invites.

    Take the live file and put the backup's *rows* into it while leaving the live
    anchor in place — the shape you get from restoring one table, or from a copy
    that ran while a write was in flight. One row of chain under two rows' worth
    of anchor is a tail truncation, and it must raise.

    **What catches it is the anchor's hash, not its count**, and that is worth
    saying because the count is what the anchor is usually credited with. The
    surviving row's hash is not the hash the anchor names, so this shape fails on
    the link comparison alone — deleting the ``count`` comparison from ``_verify``
    leaves this test green. The count earns its keep against a *directly edited
    anchor*, where the rows are untouched and the hash still matches, and that is
    gated in ``tests/test_consent.py`` rather than here.
    """
    live, backup = midseason
    chain = consent_chain("kid")
    old_rows = sqlite3.connect(backup).execute(
        "SELECT seq, row FROM consent_chain WHERE chain = ? ORDER BY seq", (chain,)
    ).fetchall()
    assert len(old_rows) == 1

    conn = sqlite3.connect(live)
    conn.execute("DELETE FROM consent_chain WHERE chain = ?", (chain,))
    conn.executemany(
        "INSERT INTO consent_chain(chain, seq, row) VALUES (?, ?, ?)",
        [(chain, seq, row) for seq, row in old_rows])
    conn.commit()
    conn.close()

    roster = ConsentedRoster(Store(live))
    with pytest.raises(ChainTamperError):
        roster.verify("kid")
    with pytest.raises(ChainTamperError):
        roster.verify()                                # the sweep catches it too
    # and the gate denies rather than serving what survived
    assert roster.permitted("kid", "local_only") is False


def test_a_restore_that_dropped_the_anchors_is_detected(midseason):
    """The other half of the same partial restore: rows without their anchor.

    An anchorless chain is not "unverified", it is tampered — the anchor is
    written in the same transaction as its row, so a chain with rows and no
    anchor is a state no honest write produces.
    """
    live, _ = midseason
    conn = sqlite3.connect(live)
    conn.execute("DELETE FROM consent_anchor")
    conn.commit()
    conn.close()

    roster = ConsentedRoster(Store(live))
    with pytest.raises(ChainTamperError):
        roster.verify("kid")
    assert roster.permitted("kid", "local_only") is False


def test_a_restore_cannot_be_extended_into_looking_clean(midseason):
    """A tampered restore must stay tampered.

    The failure this refuses is self-healing: append one honest row to a
    truncated chain, the anchor advances to match, and the file verifies clean
    with the deleted history gone and nothing left to say so. The core refuses
    to extend a chain that does not verify, so the tamper survives the next
    legitimate write instead of being laundered by it.
    """
    live, _ = midseason
    chain = consent_chain("kid")
    conn = sqlite3.connect(live)
    conn.execute("DELETE FROM consent_chain WHERE chain = ? AND seq = 2", (chain,))
    conn.commit()
    conn.close()

    roster = ConsentedRoster(Store(live))
    with pytest.raises(ChainTamperError):
        roster.revoke_use("kid", "local_only", "parent")
    with pytest.raises(ChainTamperError):
        roster.verify("kid")
