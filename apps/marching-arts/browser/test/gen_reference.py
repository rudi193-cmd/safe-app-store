#!/usr/bin/env python3
"""Generate the differential-test reference from the Python authorization core.

Writes ``browser/test/reference.json``: a randomised corpus of principals, facts
and grants, together with everything the Python resolver produces over it —
compiled predicates, bound parameters, ``COUNT(*)`` results, row sets, sort
orders, pages and subject lists. ``differential.mjs`` replays the identical
corpus through the TypeScript port on SQLite-WASM and asserts agreement.

Nothing here is written to test the port's own idea of correct. The Python core
in ``marching_arts/`` is the decided semantics; this file only records what it
does. If the two disagree, Python is right by construction.

Five tiers, following the harness shape in ``apps/field-acoustics/kernel/test``:

  1. constants   — band integers, DERIVE_AT, NEVER_SERVED, DENY_ALL, SORTABLE,
                   and the migration DDL, compared byte-for-byte.
  2. compiler    — randomised Rule lists compiled in isolation and evaluated
                   against a scratch table of integers, exactly as
                   ``tests/test_rules.py`` does. Catches a precedence error
                   without any of the policy in the way.
  3. policy      — the rules ``Policy.rules()`` emits per principal, as SQL text
                   plus parameters, so a drifted fragment is located precisely.
  4. store       — the adversarial query battery from ``tests/test_gate.py``
                   over every (world, principal) pair: hidden rows under COUNT,
                   caller filters that try to widen, payload probes, every
                   sortable column ascending and descending, pagination, and
                   refused-versus-nonexistent indistinguishability.
  5. schema      — writes the schema must refuse: a blank source, a whitespace
                   source, a sealed grant with no signer, a band out of range.

Which Python is "the" Python
---------------------------

By default this reads ``marching_arts/`` **from the working tree**. That is the
gate: when the core changes and the port does not, the suite fails, which is the
whole reason the suite exists. If the working tree differs from ``HEAD`` the
generator says so on stderr, because a local edit silently redefining the
reference is exactly the failure mode this project keeps rediscovering.

``--rev REV`` materialises the core at a git revision instead, for the case
where the core is mid-edit by someone else and you need a stable target. Using
it is a deliberate act and the revision is recorded in the output.

Run from anywhere:  python3 browser/test/gen_reference.py [--rev HEAD]
Stdlib only, matching the package it tests.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(os.path.dirname(HERE))
CORE_DIR = os.path.join(APP_ROOT, "marching_arts")


def _git(*args: str) -> "str | None":
    try:
        return subprocess.run(
            ["git", "-C", APP_ROOT, *args],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _repo_relative() -> "str | None":
    top = _git("rev-parse", "--show-toplevel")
    if not top:
        return None
    return os.path.relpath(CORE_DIR, top.strip()).replace(os.sep, "/")


def select_core(rev: "str | None") -> dict:
    """Put the chosen ``marching_arts`` package on ``sys.path``.

    Returns a provenance record that goes into the reference file, so a reader
    of reference.json can always tell what it was generated from.
    """
    rel = _repo_relative()
    if rev is None:
        dirty = False
        if rel:
            status = _git("status", "--porcelain", "--", CORE_DIR)
            dirty = bool(status and status.strip())
        if dirty:
            sys.stderr.write(
                "WARNING: marching_arts/ has uncommitted changes. The reference "
                "is being generated from the working tree, which is the intended "
                "default, but it means this file records semantics that are not "
                "in any commit. Use --rev HEAD to pin.\n")
        sys.path.insert(0, APP_ROOT)
        return {"source": "worktree", "path": CORE_DIR, "dirty": dirty}

    if not rel:
        raise SystemExit("--rev given but this is not a git checkout")
    resolved = _git("rev-parse", rev)
    if not resolved:
        raise SystemExit("cannot resolve revision %r" % rev)
    resolved = resolved.strip()
    listing = _git("ls-tree", "-r", "--full-name", "--name-only", resolved, "--", ":/%s" % rel)
    if not listing or not listing.strip():
        raise SystemExit("no %s in %s" % (rel, resolved))

    tmp = tempfile.mkdtemp(prefix="marching-arts-core-")
    root = os.path.join(tmp, "root")
    files = []
    for path in listing.split("\n"):
        path = path.strip()
        if not path or not path.endswith(".py"):
            continue
        blob = _git("show", "%s:%s" % (resolved, path))
        if blob is None:
            raise SystemExit("cannot read %s:%s" % (resolved, path))
        # Land the package at the root of the sys.path entry, stripping the
        # repo-relative prefix above marching_arts/.
        inner = os.path.relpath(path, os.path.dirname(rel)).replace("/", os.sep)
        target = os.path.join(root, inner)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as fh:
            fh.write(blob)
        files.append(inner.replace(os.sep, "/"))

    sys.path.insert(0, root)
    return {"source": "git", "rev": rev, "commit": resolved, "path": root,
            "files": sorted(files)}


_ARGS = argparse.ArgumentParser(description=__doc__)
_ARGS.add_argument("--rev", default=None,
                   help="generate against marching_arts/ at this git revision "
                        "instead of the working tree")
_ARGS.add_argument("-o", "--out", default=None, help="output path")
OPTS = _ARGS.parse_args()
CORE = select_core(OPTS.rev)

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402
from marching_arts.bands import DERIVE_AT, NEVER_SERVED  # noqa: E402
from marching_arts.policy import Policy  # noqa: E402
from marching_arts.rules import (  # noqa: E402
    ALLOW_ALL,
    DENY_ALL,
    Effect,
    Rule,
    compile_rules,
    explain,
)
from marching_arts.schema import MIGRATIONS  # noqa: E402
from marching_arts.store import SORTABLE  # noqa: E402

OUT = OPTS.out or os.path.join(HERE, "reference.json")
SEED = 20260729

#: Enough that a coincidence has to hold across all of them.
N_WORLDS = 14
N_COMPILER_CASES = 240
#: Scratch table for the compiler tier: integers 0..SCRATCH_N-1.
SCRATCH_N = 24

SOURCES = ["rehearsal log", "consent form", "roster import", "staff note", "  padded  "]
STATES = [GrantState.SEALED.value, GrantState.DRAFT.value, GrantState.PENDING.value]


# ── tier 2: the compiler in isolation ───────────────────────────────────────
def scratch_rows(predicate: str, params: dict) -> list:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t(n INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(SCRATCH_N)])
    return [r[0] for r in conn.execute(
        "SELECT n FROM t WHERE %s ORDER BY n" % predicate, params)]


def random_fragment(rng: random.Random) -> "tuple[str, dict]":
    """A fragment over column ``n``, sometimes parameterised.

    Two rules in the same list may both use a parameter called ``v`` — that is
    the point of per-rule scoping, so the generator produces the collision on
    purpose rather than avoiding it.
    """
    kind = rng.randrange(7)
    if kind == 0:
        return "n < {v}", {"v": rng.randrange(SCRATCH_N)}
    if kind == 1:
        return "n > {v}", {"v": rng.randrange(SCRATCH_N)}
    if kind == 2:
        return "n = {v}", {"v": rng.randrange(SCRATCH_N)}
    if kind == 3:
        return "n >= {v} AND n <= {w}", {
            "v": rng.randrange(SCRATCH_N),
            "w": rng.randrange(SCRATCH_N),
        }
    if kind == 4:
        # An un-parenthesised OR inside a fragment: the compiler wraps every
        # fragment in its own parens, and if it ever stopped, this is the case
        # whose result changes.
        return "n = {v} OR n = {w}", {
            "v": rng.randrange(SCRATCH_N),
            "w": rng.randrange(SCRATCH_N),
        }
    if kind == 5:
        return "n %% {v} = {w}" % (), {"v": rng.randint(2, 5), "w": rng.randrange(2)}
    return "n IN (%s)" % ", ".join(
        str(rng.randrange(SCRATCH_N)) for _ in range(rng.randint(1, 4))
    ), {}


def rule_dict(r: Rule) -> dict:
    return {"effect": r.effect.value, "sql": r.sql, "params": r.params, "why": r.why}


def compiler_cases(rng: random.Random) -> list:
    cases = []

    def emit(name, rules):
        sql, params = compile_rules(rules)
        cases.append({
            "name": name,
            "rules": [rule_dict(r) for r in rules],
            "sql": sql,
            "params": params,
            "rows": scratch_rows(sql, params),
            "explain": explain(rules),
        })

    # The named cases from tests/test_rules.py, verbatim, so a reader can see
    # the correspondence.
    emit("no_allows_denies_everything", [])
    emit("denies_alone_still_deny_everything", [Rule(Effect.DENY, "n = 3")])
    emit("allows_are_unioned", [
        Rule(Effect.ALLOW, "n < 2"), Rule(Effect.ALLOW, "n > 7")])
    emit("deny_negates_the_union_not_the_first_term", [
        Rule(Effect.ALLOW, "n < 2"), Rule(Effect.ALLOW, "n > 7"),
        Rule(Effect.DENY, "n = 1"), Rule(Effect.DENY, "n = 8")])
    emit("a_later_allow_cannot_reopen_a_denied_row", [
        Rule(Effect.DENY, "n = 5"), Rule(Effect.ALLOW, "n >= 0"),
        Rule(Effect.ALLOW, "n = 5")])
    emit("parameters_are_scoped_per_rule", [
        Rule(Effect.ALLOW, "n = {v}", {"v": 3}), Rule(Effect.ALLOW, "n = {v}", {"v": 6})])
    emit("single_allow_needs_no_extra_grouping", [Rule(Effect.ALLOW, "n = 1")])
    emit("explain_reports_reasons_in_order", [
        Rule(Effect.ALLOW, "n < 2", why="own record"),
        Rule(Effect.DENY, "n = 1", why="routed elsewhere"),
        Rule(Effect.ALLOW, "n = 9")])
    # A deny-only list carries parameters that must be *dropped* along with the
    # deny terms: compile_rules returns a fresh {} when there are no allows.
    emit("deny_only_drops_its_parameters", [
        Rule(Effect.DENY, "n = {v}", {"v": 4}), Rule(Effect.DENY, "n = {v}", {"v": 9})])

    for i in range(N_COMPILER_CASES):
        n_allow = rng.randrange(0, 4)
        n_deny = rng.randrange(0, 4)
        rules = []
        for _ in range(n_allow):
            sql, params = random_fragment(rng)
            rules.append(Rule(Effect.ALLOW, sql, params, rng.choice(["", "because"])))
        for _ in range(n_deny):
            sql, params = random_fragment(rng)
            rules.append(Rule(Effect.DENY, sql, params, rng.choice(["", "withheld"])))
        rng.shuffle(rules)
        emit("random_%03d" % i, rules)
    return cases


# ── tier 3+4: worlds, principals, and the query battery ─────────────────────
def random_world(rng: random.Random, index: int) -> dict:
    people = ["p%d" % i for i in range(rng.randint(3, 7))]
    facts = []
    for i in range(rng.randint(12, 40)):
        band = int(rng.choice(list(Band)))
        has_payload = rng.random() < 0.85
        facts.append({
            "subject_id": rng.choice(people),
            "band": band,
            "source": rng.choice(SOURCES),
            "payload": ("payload %d-%d" % (index, i)) if has_payload else None,
            "instruction": ("do %d-%d" % (index, i)) if rng.random() < 0.6 else None,
        })
    grants = []
    for _ in range(rng.randint(0, 10)):
        state = rng.choice(STATES)
        subject = rng.choice(people)
        grantee = rng.choice(people + ["leader", "stranger"])
        grants.append({
            "subject_id": subject,
            "grantee_id": grantee,
            "band": int(rng.choice(list(Band))),
            "state": state,
            "source": rng.choice(SOURCES),
            # Required when sealed; the schema refuses a sealed grant with no
            # signer, so the generator never produces one.
            "sealed_by": "guardian" if state == GrantState.SEALED.value else (
                "staff" if rng.random() < 0.4 else None),
        })
    principals = list(people) + ["leader", "stranger", "", "nobody"]
    return {"name": "w%02d" % index, "people": people, "facts": facts,
            "grants": grants, "principals": principals}


def build_store(world: dict) -> Store:
    store = Store(":memory:")
    for f in world["facts"]:
        store.record_fact(f["subject_id"], f["band"], f["source"],
                          payload=f["payload"], instruction=f["instruction"])
    for g in world["grants"]:
        store.record_grant(g["subject_id"], g["grantee_id"], g["band"],
                           g["state"], g["source"], sealed_by=g["sealed_by"])
    return store


def fact_tuple(f) -> list:
    return [f.id, f.subject_id, f.band, f.payload, f.instruction, f.source]


def query_battery(world: dict, rng: random.Random) -> list:
    """Every adversarial shape from tests/test_gate.py, plus the sort matrix.

    Returned as descriptions; the results are filled in per principal.
    """
    people = world["people"]
    subjects_present = sorted({f["subject_id"] for f in world["facts"]})
    payloads = [f["payload"] for f in world["facts"] if f["payload"]]
    battery = [
        {"kind": "count"},
        {"kind": "visible"},
        {"kind": "subjects"},
        # A caller filter that tries to widen. ANDed inside the predicate, so
        # the classic OR 1=1 narrows nothing and reveals nothing.
        {"kind": "count", "where": "1 = 1 OR 1 = 1"},
        {"kind": "visible", "where": "1 = 1 OR 1 = 1"},
        {"kind": "visible", "where": "1 = 0 OR 1 = 1"},
        # A filter that tries to escape its parentheses.
        {"kind": "count", "where": "facts.band >= 0 OR facts.band < 0"},
        # LIMIT 0 — an empty page must be empty, not "everything".
        {"kind": "visible", "limit": 0},
    ]
    # Refused vs nonexistent: probe every subject that exists, plus two that do
    # not. For a principal who may not see a subject, the two must be identical.
    for who in subjects_present + ["no-such-person", ""]:
        battery.append({"kind": "count", "where": "facts.subject_id = :who",
                        "params": {"who": who}})
        battery.append({"kind": "visible", "where": "facts.subject_id = :who",
                        "params": {"who": who}})
    # Payload probing: a payload that exists somewhere, and one that does not.
    for p in (payloads[:2] + ["no such row"]):
        battery.append({"kind": "count", "where": "facts.payload = :p",
                        "params": {"p": p}})
    # Every band, including the never-served one. A grant that reaches L5 must
    # still return zero.
    for band in list(Band):
        battery.append({"kind": "count", "where": "facts.band = :b",
                        "params": {"b": int(band)}})
        battery.append({"kind": "visible", "where": "facts.band = :b",
                        "params": {"b": int(band)}})
    # The sort matrix.
    for order_by in sorted(SORTABLE):
        for descending in (False, True):
            battery.append({"kind": "visible", "order_by": order_by,
                            "descending": descending})
    # Pagination on the unique key, so pages are unambiguous and denseness is
    # checkable: sum of page lengths must equal COUNT(*).
    for offset in (0, 1, 2, 4, 8):
        battery.append({"kind": "visible", "order_by": "id", "limit": 2,
                        "offset": offset})
    battery.append({"kind": "visible", "order_by": "id", "descending": True,
                    "limit": 3, "offset": 1})
    # A narrowing filter combined with pagination and a descending sort.
    if people:
        battery.append({"kind": "visible", "where": "facts.subject_id = :who",
                        "params": {"who": rng.choice(people)},
                        "order_by": "band", "descending": True, "limit": 5,
                        "offset": 0})
    return battery


def run_case(store: Store, principal: Principal, q: dict) -> dict:
    where = q.get("where")
    params = q.get("params")
    predicate, bound = store.predicate(principal, where, params)
    out = {
        "kind": q["kind"],
        "where": where,
        "params": params,
        "order_by": q.get("order_by"),
        "descending": q.get("descending"),
        "limit": q.get("limit"),
        "offset": q.get("offset"),
        "predicate": predicate,
        "predicateParams": bound,
    }
    if q["kind"] == "count":
        out["count"] = store.count(principal, where=where, params=params)
    elif q["kind"] == "subjects":
        out["subjects"] = store.subjects(principal)
    else:
        kwargs = {"where": where, "params": params}
        if q.get("order_by") is not None:
            kwargs["order_by"] = q["order_by"]
        if q.get("descending") is not None:
            kwargs["descending"] = q["descending"]
        if q.get("limit") is not None:
            kwargs["limit"] = q["limit"]
            kwargs["offset"] = q.get("offset") or 0
        rows = store.visible(principal, **kwargs)
        out["rows"] = [fact_tuple(f) for f in rows]
        key = {"id": 0, "subject_id": 1, "band": 2}.get(q.get("order_by") or "id")
        # created_at has no unique key and ties are ordered arbitrarily by
        # SQLite; the comparator checks the multiset and the key sequence there
        # rather than the exact row order. Recorded so it is visible.
        out["orderKeyUnique"] = (q.get("order_by") or "id") == "id"
        out["orderKeys"] = ([r[key] for r in out["rows"]] if key is not None else None)
    return out


# ── tier 5: writes the schema must refuse ───────────────────────────────────
def rejection_cases() -> list:
    return [
        {"name": "fact_with_blank_source", "op": "fact",
         "args": {"subject_id": "p0", "band": 1, "source": "", "payload": "x"}},
        {"name": "fact_with_whitespace_source", "op": "fact",
         "args": {"subject_id": "p0", "band": 1, "source": "   ", "payload": "x"}},
        {"name": "fact_with_band_above_range", "op": "fact",
         "args": {"subject_id": "p0", "band": int(max(Band)) + 1, "source": "s"}},
        {"name": "fact_with_negative_band", "op": "fact",
         "args": {"subject_id": "p0", "band": -1, "source": "s"}},
        {"name": "sealed_grant_without_signer", "op": "grant",
         "args": {"subject_id": "p0", "grantee_id": "p1", "band": 2,
                  "state": "sealed", "source": "form", "sealed_by": None}},
        {"name": "sealed_grant_with_blank_signer", "op": "grant",
         "args": {"subject_id": "p0", "grantee_id": "p1", "band": 2,
                  "state": "sealed", "source": "form", "sealed_by": "  "}},
        {"name": "grant_with_unknown_state", "op": "grant",
         "args": {"subject_id": "p0", "grantee_id": "p1", "band": 2,
                  "state": "approved", "source": "form", "sealed_by": "guardian"}},
        {"name": "grant_with_blank_source", "op": "grant",
         "args": {"subject_id": "p0", "grantee_id": "p1", "band": 2,
                  "state": "draft", "source": "", "sealed_by": None}},
    ]


def verify_rejections(cases: list) -> list:
    """Prove each rejection case really is refused *by Python* before asking the
    port to refuse it. A case that Python accepts is a bug in this generator,
    not a gate."""
    out = []
    for case in cases:
        store = Store(":memory:")
        a = case["args"]
        try:
            if case["op"] == "fact":
                store.record_fact(a["subject_id"], a["band"], a["source"],
                                  payload=a.get("payload"),
                                  instruction=a.get("instruction"))
            else:
                store.record_grant(a["subject_id"], a["grantee_id"], a["band"],
                                   a["state"], a["source"],
                                   sealed_by=a.get("sealed_by"))
        except sqlite3.IntegrityError as exc:
            out.append({**case, "rejected": True, "error": type(exc).__name__,
                        "message": str(exc)})
            continue
        raise SystemExit(
            "generator bug: %s was accepted by the Python core; it is not a gate"
            % case["name"])
    return out


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    rng = random.Random(SEED)
    policy = Policy()

    worlds = []
    n_queries = 0
    for i in range(N_WORLDS):
        world = random_world(rng, i)
        store = build_store(world)
        battery = query_battery(world, rng)
        cases = []
        for person in world["principals"]:
            principal = Principal(person)
            rules = policy.rules(principal)
            predicate, params = compile_rules(rules)
            results = [run_case(store, principal, q) for q in battery]
            n_queries += len(results)
            cases.append({
                "principal": person,
                "rules": [rule_dict(r) for r in rules],
                "explain": explain(rules),
                "predicate": predicate,
                "predicateParams": params,
                "projection": policy.projection(principal),
                "projectionParams": policy.projection_params(principal),
                "queries": results,
            })
        worlds.append({
            "name": world["name"],
            "facts": world["facts"],
            "grants": world["grants"],
            "cases": cases,
        })

    payload = {
        "generator": "browser/test/gen_reference.py",
        "core": CORE,
        "seed": SEED,
        "sqliteVersion": sqlite3.sqlite_version,
        "constants": {
            "bands": {b.name: int(b) for b in Band},
            "deriveAt": int(DERIVE_AT),
            "neverServed": sorted(int(b) for b in NEVER_SERVED),
            "denyAll": DENY_ALL,
            "allowAll": ALLOW_ALL,
            "sortable": sorted(SORTABLE),
            "migrations": [[name, sql] for name, sql in MIGRATIONS],
        },
        "compiler": compiler_cases(rng),
        "worlds": worlds,
        "rejections": verify_rejections(rejection_cases()),
    }

    with open(OUT, "w") as fh:
        json.dump(payload, fh)

    print("wrote %s" % OUT)
    print("  core: %s" % json.dumps(CORE))
    print("  %d compiler cases over a %d-row scratch table"
          % (len(payload["compiler"]), SCRATCH_N))
    print("  %d worlds, %d principal cases, %d store queries"
          % (len(worlds), sum(len(w["cases"]) for w in worlds), n_queries))
    print("  %d schema rejections, each confirmed refused by Python"
          % len(payload["rejections"]))


if __name__ == "__main__":
    main()
