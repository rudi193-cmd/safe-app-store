#!/usr/bin/env python3
"""tools/store_reconcile.py — the declared-vs-materialized store reconciler.

The inverse organ of `stores/promote_check.py`, and the healer that makes
`tools/catalog_lint.py` pass. Where lint is a fail-closed pass/fail gate that
prints errors and exits 1, the reconciler enumerates both sides of the store,
emits **one verdict per key**, and — on request — writes the **additive** fixes
that make lint green again. See docs/design/store-reconciler.md (the contract
this file is built to).

The two accounts it diffs:

  * the **declared** set — what the house says it has: `.willow/store/catalog.json`
    `apps[]`, the keeping records `stores/<major>/stored/<app_id>.json`, the
    promotion records `stores/<major>/promoted/<app_id>.json`, and the declared
    *absences* in `stores/pending.json`;
  * the **materialized** set — what is actually on disk: the `apps/<name>/`
    directories.

Verdicts (one per key, over the union of declared and materialized keys):

  missing         declared with a resolvable local path, not on disk.
  source_changed  both present, the canonical fact-projection differs.
  up_to_date      both present, projections equal.
  stale           on disk, not declared, not in pending.json.
  declared_absent named in pending.json — an absence with a recorded reason is
                  not a drift, so it is never reported missing or stale.

`source_changed` is a content hash over a **canonical fact-projection**
`{app_id, tier, sorted majors, status/state, path-basename}`, computed fresh on
each side — never mtime (a checkout stamps every file the same instant), never
`version` (sparse and unenforced), never a byte-hash of the app code (the store
keeps the *record*, not a copy of the code; hashing the bytes measures the wrong
thing). It fires on exactly the disagreements catalog_lint enumerates — catalog
`majors` != keeping-record `majors`, catalog `status` != record `state`, manifest
`app_id` != directory name — reframed from error strings into a verdict that
names the diverging fields.

Apply (`--apply`) is idempotent and additive-only: it realigns a catalog entry's
*generated* fields (tier/majors/status) to the keeping record, and — with
`--heal-stale` — writes a blank pending stub for a stale directory (a human
completes the `reason`). It never removes a directory or a record without
`--allow-delete`, and even then removal is archive-not-delete (store rule 4). A
`missing` key cannot be healed — code is not synthesizable from a metadata
record — so it is routed to a first-class `skipped` bucket, never silently
dropped.

The core (`reconcile` + `apply`) is store-agnostic: it takes injected
enumerators, two fingerprint functions, an exempt set, and per-verdict actions.
The store's seams live at the bottom of this file. almanac-data's
`propagate-engine.sh` is the same reconciler with byte-identity and a `cp`
materializer — that shared-seam property is proven in the test suite.

Usage:
    tools/store_reconcile.py               # --check (default): drift report
    tools/store_reconcile.py --apply       # additive heal, print ApplyResult
    tools/store_reconcile.py --apply --heal-stale
    tools/store_reconcile.py --apply --allow-delete
    tools/store_reconcile.py --json
    tools/store_reconcile.py --strict      # accepted, for house-convention parity

Stdlib only, same discipline as catalog_lint.py / promote_check.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent

# The drift verdicts — the ones --check treats as "not reconciled".
DRIFT_VERDICTS = ("missing", "source_changed", "stale")


class CorpusError(Exception):
    """The declared corpus could not be read (unreadable/malformed catalog).

    A reconciler that cannot read one side must not report a false all-clear —
    same fail-closed philosophy as catalog_lint / readiness_drift."""


# ── the core: store-agnostic, seams injected ─────────────────────────────────


@dataclass
class Verdict:
    key: str
    verdict: str
    declared_fp: dict | None = None
    materialized_fp: dict | None = None
    diverging: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"key": self.key, "verdict": self.verdict}
        if self.diverging:
            out["diverging"] = {
                k: {"declared": d, "materialized": m}
                for k, (d, m) in self.diverging.items()
            }
        return out


@dataclass
class Report:
    verdicts: list[Verdict]

    def by_verdict(self) -> dict[str, list[Verdict]]:
        out: dict[str, list[Verdict]] = {}
        for v in self.verdicts:
            out.setdefault(v.verdict, []).append(v)
        return out

    def has_drift(self) -> bool:
        return any(v.verdict in DRIFT_VERDICTS for v in self.verdicts)

    def to_dict(self) -> dict:
        buckets = self.by_verdict()
        return {
            "verdicts": [v.to_dict() for v in self.verdicts],
            "counts": {k: len(v) for k, v in sorted(buckets.items())},
        }


def _canonical(projection: dict) -> str:
    """A stable content hash of a fact-projection. The projection is the fact;
    the hash is just how two of them are compared for the record and printed."""
    blob = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def reconcile(
    declared: dict,
    materialized: dict,
    *,
    fingerprint_declared: Callable[[object], dict],
    fingerprint_materialized: Callable[[object], dict],
    exempt: frozenset = frozenset(),
) -> Report:
    """Walk the union of keys once; every key lands in exactly one bucket.

    `fingerprint_*` return the canonical fact-projection (a dict) for their
    side; equality of the two projections is `up_to_date`, inequality is
    `source_changed` carrying the fields that diverged. A key in `exempt`
    (the store's pending.json absences) is `declared_absent` and is never
    reported missing or stale — an absence with a recorded reason is a value,
    not a gap."""
    keys = sorted(set(declared) | set(materialized) | set(exempt))
    verdicts: list[Verdict] = []
    for key in keys:
        if key in exempt:
            verdicts.append(Verdict(key, "declared_absent"))
            continue
        d_present = key in declared
        m_present = key in materialized
        if d_present and not m_present:
            verdicts.append(Verdict(key, "missing"))
        elif m_present and not d_present:
            verdicts.append(Verdict(key, "stale"))
        else:
            fd = fingerprint_declared(declared[key])
            fm = fingerprint_materialized(materialized[key])
            if fd == fm:
                verdicts.append(Verdict(key, "up_to_date", fd, fm))
            else:
                diverging = {
                    k: (fd.get(k), fm.get(k))
                    for k in sorted(set(fd) | set(fm))
                    if fd.get(k) != fm.get(k)
                }
                verdicts.append(Verdict(key, "source_changed", fd, fm, diverging))
    return Report(verdicts)


@dataclass
class ActionResult:
    disposition: str  # "applied" | "skipped" | "noop"
    detail: str = ""


@dataclass
class ApplyResult:
    applied: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    noop: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"applied": self.applied, "skipped": self.skipped, "noop": self.noop}


def apply(
    report: Report,
    *,
    actions: dict[str, Callable[[Verdict, dict], ActionResult]],
    opts: dict | None = None,
) -> ApplyResult:
    """Run the per-verdict `actions` over a report. A verdict with no action
    (up_to_date, declared_absent) is a `noop`. Each key produces exactly one
    ApplyResult entry — applied (an action taken), skipped (a reason it was
    not), or noop — so a partial apply is always fully accounted for."""
    opts = opts or {}
    result = ApplyResult()
    for v in report.verdicts:
        handler = actions.get(v.verdict)
        if handler is None:
            result.noop.append({"key": v.key, "verdict": v.verdict, "action": "noop"})
            continue
        res = handler(v, opts)
        entry = {"key": v.key, "verdict": v.verdict}
        if res.disposition == "applied":
            entry["action"] = res.detail
            result.applied.append(entry)
        elif res.disposition == "skipped":
            entry["reason"] = res.detail
            result.skipped.append(entry)
        else:
            entry["action"] = res.detail or "noop"
            result.noop.append(entry)
    return result


# ── the store's seams ────────────────────────────────────────────────────────


def _real_majors(repo: Path) -> set[str]:
    stores_dir = repo / "stores"
    if not stores_dir.is_dir():
        return set()
    return {
        d.name
        for d in stores_dir.iterdir()
        if d.is_dir() and (d / "stored").is_dir() and (d / "promoted").is_dir()
    }


def _load_stored_records(repo: Path) -> dict[str, dict]:
    """Fail-closed like catalog.json: a keeping record that cannot be read or
    parsed must not be silently dropped — a truncated record has previously
    let --apply realign a catalog entry away from the tier it should hold."""
    out: dict[str, dict] = {}
    for major in sorted(_real_majors(repo)):
        for rp in sorted((repo / "stores" / major / "stored").glob("*.json")):
            try:
                rec = json.loads(rp.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CorpusError(
                    f"{rp.relative_to(repo)}: unreadable/malformed keeping record: {exc}"
                ) from exc
            if rec.get("app_id"):
                out[rec["app_id"]] = rec
    return out


def _load_promoted_records(repo: Path) -> dict[str, tuple[str, dict]]:
    """Fail-closed, same reasoning as `_load_stored_records`."""
    out: dict[str, tuple[str, dict]] = {}
    for major in sorted(_real_majors(repo)):
        for rp in sorted((repo / "stores" / major / "promoted").glob("*.json")):
            try:
                rec = json.loads(rp.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CorpusError(
                    f"{rp.relative_to(repo)}: unreadable/malformed promoted record: {exc}"
                ) from exc
            if rec.get("app_id"):
                out[rec["app_id"]] = (major, rec)
    return out


def _load_pending_ids(repo: Path) -> set[str]:
    """Fail-closed, same reasoning as `_load_stored_records` — an unreadable
    pending.json used to be silently emptied, which would report every
    pending app as `stale`/`missing` for the wrong reason (a read failure)
    rather than refusing outright.

    Only ids with BOTH `reason` and `blocked_on` recorded are exempt
    (`declared_absent`) — matching catalog_lint's lint_records(), which
    errors on a pending entry missing either field. An entry that names an
    app but not why it's absent is not a recorded absence; it must remain a
    flagged (`missing`/`stale`) verdict, not a silent exemption.
    """
    p = repo / "stores" / "pending.json"
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"stores/pending.json unreadable/malformed: {exc}") from exc
    return {
        e.get("app_id") for e in data.get("pending", [])
        if e.get("app_id") and e.get("reason") and e.get("blocked_on")
    }


def project_declared(entry: dict, *, archived: bool = False) -> dict:
    """The declared fact-projection, read off the catalog entry — the facts the
    catalog *claims*: its id, tier, sorted majors, status, and the basename of
    the local path it names. A `tier: promoted` entry carries no comparable
    state (promoted records have none), so status is dropped for it — the same
    scoping catalog_lint's lint_generated_fields() applies.

    `archived` is decided by the caller from BOTH sides (catalog_lint.py:411's
    scoping is per-side; here it must be per-key) — see
    `_compute_cross_side_flags`. A key is archived-exempt the moment EITHER
    side calls it archived, so a keeping record that drifts off `archived`
    while the catalog still says `archived` (a human decision) is never
    reported `source_changed` and never realigned out from under it.
    """
    cat = entry["catalog"]
    tier = cat.get("tier")
    basename = Path(cat["path"]).name if cat.get("path") else None
    if archived or cat.get("status") == "archived":
        return {"app_id": cat.get("id"), "tier": None, "majors": [],
                "status": "archived", "path_basename": basename}
    majors = cat.get("majors") or []
    return {
        "app_id": cat.get("id"),
        "tier": tier,
        "majors": sorted(majors),
        # Raw (unsorted) order too — catalog_lint compares the majors list
        # ordered; the sorted `majors` field alone would miss an order-only
        # drift (same set, different order) that lint still fails on.
        "majors_order": tuple(majors),
        "status": None if tier == "promoted" else cat.get("status"),
        "path_basename": basename,
        # The declared side has no notion of a manifest; it simply expects
        # there to be no problem. `manifest_bad` (computed cross-side, same
        # as `archived`) is what makes this diverge from the materialized
        # side's actual answer.
        "manifest_ok": True,
    }


def project_materialized(m: dict, *, archived: bool = False, manifest_bad: bool = False) -> dict:
    """The same shape, derived from disk: the directory basename, the manifest's
    app_id (falling back to the basename when there is no manifest — the same
    scoping lint uses), and the majors/state the keeping (or promoted) record
    for that directory yields. Computed fresh; never persisted.

    `archived` and `manifest_bad` are cross-side facts the caller precomputes
    (see `_compute_cross_side_flags`) — this function only ever sees its own
    entry, so it cannot itself know the catalog's status or the archived state
    the *other* side declares.
    """
    manifest = m.get("manifest") or {}
    keeping = m.get("keeping")
    promoted = m.get("promoted")
    app_id = manifest.get("app_id") or m["dir_basename"]
    # Archived — mirror project_declared: identity facts only, generated fields
    # dropped, so an archived app is never a source_changed the lint would skip.
    if archived or (keeping or {}).get("state") == "archived":
        return {"app_id": app_id, "tier": None, "majors": [],
                "status": "archived", "path_basename": m["dir_basename"]}
    # Keeping record wins when both exist — the same precedence catalog_lint's
    # lint_generated_fields() applies (it checks `stored` before `promoted`): a
    # playground app can keep a promoted record from an earlier lift while its
    # standing state is still read from the keeping record.
    if keeping:
        majors = keeping.get("majors") or []
        base = {
            "app_id": app_id,
            "tier": "playground",
            "majors": sorted(majors),
            "majors_order": tuple(majors),
            "status": keeping.get("state"),
            "path_basename": m["dir_basename"],
        }
    elif promoted:
        major = promoted.get("major")
        majors = [major] if major else []
        base = {
            "app_id": app_id,
            "tier": "promoted",
            "majors": sorted(majors),
            "majors_order": tuple(majors),
            "status": None,
            "path_basename": m["dir_basename"],
        }
    else:
        base = {
            "app_id": app_id,
            "tier": "playground",
            "majors": [],
            "majors_order": (),
            "status": None,
            "path_basename": m["dir_basename"],
        }
    base["manifest_ok"] = not manifest_bad
    return base


def _compute_cross_side_flags(declared: dict, materialized: dict) -> tuple[frozenset, frozenset]:
    """Facts neither `project_declared` nor `project_materialized` can compute
    alone, because each only sees its own side's entry.

    * `archived_keys` — a key is archived the moment EITHER the catalog status
      or the keeping record's state says so (finding: archived scoping was
      per-side, letting --apply un-archive a catalog entry when only one side
      had moved off `archived`).
    * `manifest_bad_keys` — a key whose materialized manifest is missing (when
      the catalog status requires one: building/gated/stalled) or malformed
      (unconditionally, any status) — exactly what catalog_lint's manifest
      check (lint():172-188) errors on, which the old dir-name fallback let
      --check silently call `up_to_date`.
    """
    archived_keys: set = set()
    for key, d in declared.items():
        if d["catalog"].get("status") == "archived":
            archived_keys.add(key)
    for key, m in materialized.items():
        if (m.get("keeping") or {}).get("state") == "archived":
            archived_keys.add(key)

    manifest_bad_keys: set = set()
    for key in set(declared) & set(materialized):
        if key in archived_keys:
            continue
        cat_status = declared[key]["catalog"].get("status")
        m = materialized[key]
        if m.get("manifest_malformed"):
            manifest_bad_keys.add(key)
        elif m.get("manifest") is None and cat_status in ("building", "gated", "stalled"):
            manifest_bad_keys.add(key)

    return frozenset(archived_keys), frozenset(manifest_bad_keys)


def _make_fingerprint_fns(archived_keys: frozenset, manifest_bad_keys: frozenset):
    """Bind the cross-side facts into the single-arg fingerprint callables the
    store-agnostic core expects. The key is recovered from the entry itself
    (declared entries are keyed by catalog id, materialized by dir basename —
    both are carried on the entry), so the core's `Callable[[object], dict]`
    contract is untouched."""

    def fp_declared(entry: dict) -> dict:
        key = entry["catalog"].get("id")
        return project_declared(entry, archived=key in archived_keys)

    def fp_materialized(entry: dict) -> dict:
        key = entry["dir_basename"]
        return project_materialized(
            entry, archived=key in archived_keys, manifest_bad=key in manifest_bad_keys
        )

    return fp_declared, fp_materialized


def enumerate_store(repo: Path) -> tuple[dict, dict, frozenset]:
    """Build (declared, materialized, exempt) for the SAFE store. Fail-closed:
    an unreadable or malformed catalog raises CorpusError before anything is
    walked or written."""
    catalog_path = repo / ".willow" / "store" / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"catalog.json unreadable: {exc}") from exc
    apps = catalog.get("apps")
    if not isinstance(apps, list):
        raise CorpusError('catalog.json has no "apps" list')

    stored = _load_stored_records(repo)
    promoted = _load_promoted_records(repo)
    pending = _load_pending_ids(repo)

    # Declared: catalog entries that name a local path (the resolvable-in-
    # principle set). Loose external repos and pathless archived entries are
    # catalog_lint's concern, not a declared-vs-disk drift.
    declared: dict[str, dict] = {}
    for e in apps:
        if not e.get("path") or not e.get("id"):
            continue
        declared[e["id"]] = {"catalog": e, "path": e.get("path")}

    # Materialized: every apps/<dir>, carrying its manifest and the keeping/
    # promoted record that names that directory.
    materialized: dict[str, dict] = {}
    apps_dir = repo / "apps"
    if apps_dir.is_dir():
        for d in sorted(apps_dir.iterdir()):
            if not d.is_dir():
                continue
            name = d.name
            manifest = None
            manifest_malformed = False
            mp = d / "safe-app-manifest.json"
            if mp.is_file():
                try:
                    manifest = json.loads(mp.read_text())
                except json.JSONDecodeError:
                    # Malformed manifest is a per-entry lint ERROR, not a
                    # whole-corpus fail-closed condition (unlike catalog.json
                    # / keeping / promoted records) — it must surface as a
                    # flagged verdict, not silently fall back to the
                    # dir-name identity as if nothing were wrong.
                    manifest = None
                    manifest_malformed = True
            prom = promoted.get(name)
            materialized[name] = {
                "dir_basename": name,
                "manifest": manifest,
                "manifest_malformed": manifest_malformed,
                "keeping": stored.get(name),
                "promoted": prom[1] if prom else None,
            }

    return declared, materialized, frozenset(pending)


# ── the store's apply actions ────────────────────────────────────────────────


def _load_catalog(repo: Path) -> tuple[Path, dict]:
    p = repo / ".willow" / "store" / "catalog.json"
    return p, json.loads(p.read_text())


def _store_actions(repo: Path, declared: dict, materialized: dict) -> dict:
    """The store's per-verdict apply actions, closed over the enumerated maps.

    * source_changed — realign the catalog entry's *generated* fields
      (tier/majors/status) to the keeping/promoted record. That is the one
      direction the store treats as machine-owned; the keeping and promoted
      records are never rewritten.
    * missing — cannot be healed: code is not synthesizable from a metadata
      record. Routed to `skipped` (path_gone / no_materializer).
    * stale — additive only. With --allow-delete, archive the directory
      (moved, never rm — store rule 4). Otherwise, with --heal-stale, write a
      blank pending stub for a human to complete (skipped: needs_human); with
      neither flag, report skipped: would_delete.
    """

    def realign_source_changed(v: Verdict, opts: dict) -> ActionResult:
        if "manifest_ok" in v.diverging:
            # The divergence is a missing/malformed manifest, not a catalog
            # field the reconciler can regenerate — rewriting tier/majors/
            # status would not make catalog_lint green (the manifest error
            # persists), so this must not be claimed as "applied".
            return ActionResult(
                "skipped",
                "needs_human: manifest missing or malformed — cannot be "
                "healed by rewriting the catalog",
            )
        m = materialized.get(v.key) or {}
        keeping = m.get("keeping")
        promoted = m.get("promoted")
        path, catalog = _load_catalog(repo)
        changed = False
        for e in catalog.get("apps", []):
            if e.get("id") != v.key:
                continue
            if keeping:
                want = {
                    "tier": "playground",
                    # Guard against a keeping record with `majors: null` —
                    # realigning must never write a bare `null` into the
                    # catalog's majors list.
                    "majors": keeping.get("majors") or [],
                    "status": keeping.get("state"),
                }
            elif promoted:
                major = promoted.get("major")
                want = {"tier": "promoted", "majors": [major] if major else []}
            else:
                # No record to realign toward — a manifest-only divergence
                # (app_id) a machine must not "fix" by renaming a directory.
                return ActionResult("skipped", "needs_human: no keeping record to realign toward")
            for k, val in want.items():
                if e.get(k) != val:
                    e[k] = val
                    changed = True
            break
        else:
            return ActionResult("skipped", "no_catalog_entry")
        if not changed:
            return ActionResult("noop", "already aligned")
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
        return ActionResult("applied", "realigned catalog generated fields (tier/majors/status)")

    def route_missing(v: Verdict, opts: dict) -> ActionResult:
        d = declared.get(v.key) or {}
        rel = d.get("path")
        if rel and not (repo / rel).exists():
            return ActionResult("skipped", "path_gone: declared path no longer exists")
        return ActionResult("skipped", "no_materializer: code cannot be synthesized from a record")

    def heal_stale(v: Verdict, opts: dict) -> ActionResult:
        # Declared is keyed by catalog id, materialized by directory basename
        # (rule 8 says they should be equal, but an id/basename slip is
        # exactly the kind of drift this tool exists to surface — not to act
        # destructively on). If some catalog entry's `path` names this exact
        # directory, it is not stale: it is declared, just under a different
        # key than its own basename. Refuse to archive or stub it.
        declared_path_basenames = {
            Path(d["path"]).name for d in declared.values() if d.get("path")
        }
        if v.key in declared_path_basenames:
            return ActionResult(
                "skipped",
                "needs_human: directory basename matches a declared catalog "
                "path (id/basename slip) — not stale, refusing to archive or stub",
            )
        if opts.get("allow_delete"):
            src = repo / "apps" / v.key
            if not src.is_dir():
                return ActionResult("skipped", "path_gone: directory already absent")
            archive_root = repo / "_archived_apps"
            archive_root.mkdir(exist_ok=True)
            dest = archive_root / v.key
            if dest.exists():
                return ActionResult("noop", "already archived")
            src.rename(dest)
            return ActionResult("applied", f"archived (moved to _archived_apps/{v.key}) — not deleted")
        if not opts.get("heal_stale"):
            return ActionResult("skipped", "would_delete: --allow-delete not set (reported, not removed)")
        # Additive: write a blank pending stub for a human to complete. Never
        # touches the directory or any keeping/promoted record.
        pending_path = repo / "stores" / "pending.json"
        if pending_path.is_file():
            try:
                data = json.loads(pending_path.read_text())
            except json.JSONDecodeError:
                return ActionResult("skipped", "needs_human: pending.json unreadable")
        else:
            data = {"pending": []}
        entries = data.setdefault("pending", [])
        if any(e.get("app_id") == v.key for e in entries):
            return ActionResult("noop", "pending stub already present")
        entries.append({"app_id": v.key, "reason": "", "blocked_on": ""})
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return ActionResult(
            "skipped",
            "needs_human: wrote blank pending stub — a human must supply reason/blocked_on",
        )

    return {
        "source_changed": realign_source_changed,
        "missing": route_missing,
        "stale": heal_stale,
    }


# ── the store driver: enumerate → reconcile → (apply) ────────────────────────


def run_reconcile(repo: Path | None = None) -> Report:
    repo = REPO if repo is None else repo
    declared, materialized, exempt = enumerate_store(repo)
    archived_keys, manifest_bad_keys = _compute_cross_side_flags(declared, materialized)
    fp_declared, fp_materialized = _make_fingerprint_fns(archived_keys, manifest_bad_keys)
    return reconcile(
        declared,
        materialized,
        fingerprint_declared=fp_declared,
        fingerprint_materialized=fp_materialized,
        exempt=exempt,
    )


def run_apply(
    repo: Path | None = None,
    *,
    allow_delete: bool = False,
    heal_stale: bool = False,
) -> tuple[Report, ApplyResult]:
    repo = REPO if repo is None else repo
    declared, materialized, exempt = enumerate_store(repo)
    archived_keys, manifest_bad_keys = _compute_cross_side_flags(declared, materialized)
    fp_declared, fp_materialized = _make_fingerprint_fns(archived_keys, manifest_bad_keys)
    report = reconcile(
        declared,
        materialized,
        fingerprint_declared=fp_declared,
        fingerprint_materialized=fp_materialized,
        exempt=exempt,
    )
    actions = _store_actions(repo, declared, materialized)
    result = apply(
        report,
        actions=actions,
        opts={"allow_delete": allow_delete, "heal_stale": heal_stale},
    )
    return report, result


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="store_reconcile.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--apply", action="store_true", help="perform the additive apply")
    p.add_argument("--allow-delete", action="store_true",
                   help="archive (never rm) stale directories; opt-in")
    p.add_argument("--heal-stale", action="store_true",
                   help="write a blank pending stub for stale dirs (a human completes it)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true",
                   help="accepted for house-convention parity; --check is fail-closed by construction")
    return p


def _print_report(report: Report) -> None:
    icons = {
        "missing": "❌", "source_changed": "~", "up_to_date": "=",
        "stale": "+", "declared_absent": "o",
    }
    for v in report.verdicts:
        line = f"{icons.get(v.verdict, ' '):<2} {v.verdict:<15} {v.key}"
        if v.diverging:
            fields = ", ".join(sorted(v.diverging))
            line += f"  (diverging: {fields})"
        print(line)
    counts = report.to_dict()["counts"]
    print("\n" + " · ".join(f"{k}: {n}" for k, n in sorted(counts.items())))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.apply:
            report, result = run_apply(
                allow_delete=args.allow_delete, heal_stale=args.heal_stale
            )
        else:
            report = run_reconcile()
            result = None
    except CorpusError as exc:
        if args.json:
            print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        else:
            print(f"store reconcile: corpus unreadable (fail-closed): {exc}", file=sys.stderr)
        return 2

    if args.apply:
        if args.json:
            print(json.dumps(
                {"report": report.to_dict(), "apply": result.to_dict()}, indent=2))
        else:
            _print_report(report)
            print(
                f"\napplied: {len(result.applied)} · "
                f"skipped: {len(result.skipped)} · noop: {len(result.noop)}"
            )
            for e in result.applied:
                print(f"  applied  {e['key']}: {e['action']}")
            for e in result.skipped:
                print(f"  skipped  {e['key']}: {e['reason']}")
        # Non-zero when anything remains unresolved (`skipped`), so
        # `make reconcile-apply` can fail CI instead of always reporting
        # success just because the apply *ran*.
        return 1 if result.skipped else 0

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report)
    return 1 if report.has_drift() else 0


if __name__ == "__main__":
    sys.exit(main())
