"""H-8 — the living lane forgets on purpose, and proves it (bite 7).

The extension's living lane, built after reading Nestor's ledger (the check the
plan demanded, recorded in `docs/DECISION-living-lane-ledger.md`). The done-when
(`homestead/docs/PLAN-homestead-health.md` § bite 7):

* overwriting a living entry leaves **no recoverable prior** — the value store
  yields only the latest;
* the audit shows a replacement happened (an `IntegrityLog` line and
  `verify(expected_head=…)` against an off-machine head) while no log line carries
  the prior's content;
* **grepping the living store and the ledger for any subject id comes back empty**
  (H-8);
* the lane exposes **no egress at all**, purposed or otherwise.

These are written as tests, not prose. Since the extension's H-6…H-8 were never
added to `test_invariants_pending.py` (they postdate it and are unratified), there
is nothing to promote — this file lands them directly.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from homestead.keep import paths
from homestead.keep.logs import IntegrityLog
from homestead.keep.record import Sidecar

from homestead_health.living import LIVING_KIND, LivingLane
from homestead_health.roster import Roster

MODULE = Path(__file__).resolve().parent.parent / "homestead_health" / "living.py"

PRIOR = "PRIOR_WORRY_ALPHA_the-thing-that-must-be-forgotten"
LATEST = "LATEST_WORRY_BETA_the-only-thing-that-remains"


# ── no recoverable prior ─────────────────────────────────────────────────────


def test_overwriting_leaves_no_recoverable_prior(tmp_path, monkeypatch):
    """The value store yields only the latest. After a replace, `recall` is the new
    value, the cell file holds only the new value, and the prior plaintext is
    recoverable from nowhere — not the cell, not the ledger (which holds its hash)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    lane = LivingLane()

    lane.remember("sleep", PRIOR)
    lane.remember("sleep", LATEST)

    assert lane.recall("sleep") == LATEST, "only the latest survives"

    # The prior plaintext is gone from the whole household root — cell and logs.
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert PRIOR not in f.read_text(encoding="utf-8", errors="ignore"), (
                f"the forgotten value survived in {f}"
            )


def test_there_is_no_read_path_to_a_prior_value():
    """Forgetting is structural: the lane offers `recall` (latest only) and
    `replacements` (hashes, not values). No method hands back a superseded value —
    a history-of-values API is the pinned per-child record the lane refuses to be."""
    public = {n for n in dir(LivingLane) if not n.startswith("_")}
    # The public surface is exactly these; nothing that would return a prior value.
    assert public == {"remember", "recall", "things", "replacements", "verify", "head"}


# ── the replacement is provable, and content-free ────────────────────────────


def test_a_replacement_is_recorded_as_a_hash_never_the_value(tmp_path, monkeypatch):
    """One `IntegrityLog` line per forgetting, carrying the thing's ref and the
    SHA-256 of the value it replaced — never the value, never a subject."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    lane = LivingLane()

    lane.remember("sleep", PRIOR)          # first write — nothing forgotten yet
    assert lane.replacements("sleep") == []
    lane.remember("sleep", LATEST)         # replaces PRIOR — one forgetting

    entries = lane.replacements("sleep")
    assert len(entries) == 1
    entry = entries[0]
    import hashlib
    assert entry["prior_sha256"] == hashlib.sha256(PRIOR.encode()).hexdigest()
    assert entry["kind"] == LIVING_KIND and entry["thing"] == "sleep"
    # Content-free: the entry's keys are refs and a hash and chain metadata — no
    # field a value could ride in.
    assert set(entry) == {"kind", "thing", "prior_sha256", "at", "prev"}


def test_verify_catches_a_hand_edited_forgetting(tmp_path, monkeypatch):
    """The forgetting is un-forged. The head the operator records off the machine
    catches a hand-edited ledger line — the same closure bite 5's export uses, here
    for motion instead of an exported record."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    lane = LivingLane()

    lane.remember("sleep", PRIOR)
    lane.remember("sleep", LATEST)
    head = lane.head()
    assert lane.verify(expected_head=head) is True

    ledger_file = tmp_path / "logs" / "living.jsonl"
    tampered = ledger_file.read_text(encoding="utf-8").replace('"sleep"', '"forged"')
    assert tampered != ledger_file.read_text(encoding="utf-8")
    ledger_file.write_text(tampered, encoding="utf-8")

    assert lane.verify(expected_head=head) is False, (
        "a hand-edited forgetting must not verify against the off-machine head"
    )


def test_the_anchor_is_held_off_the_logs_own_tree(tmp_path, monkeypatch):
    """The head that vouches for the chain lives under `anchors/`, not beside the
    chain — the willow-mcp #280 separation, so truncating the living log does not
    clear its own witness in the same stroke."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    lane = LivingLane()
    lane.remember("sleep", PRIOR)
    lane.remember("sleep", LATEST)

    assert (tmp_path / "logs" / "living.jsonl").exists()
    assert (tmp_path / "anchors" / "living.head").exists(), "the anchor is off-tree"


# ── the thing is never the subject (H-8) ─────────────────────────────────────


def test_a_subject_id_is_refused_as_a_thing_key():
    """H-8, structurally: a `subj-NN` key is a subject wearing a thing's clothes,
    and refused. The living lane holds the thing, never the subject."""
    lane = LivingLane()
    for bad in ("subj-01", "subj-07", "subj-99"):
        with pytest.raises(ValueError):
            lane.remember(bad, "x")
        with pytest.raises(ValueError):
            lane.recall(bad)


def test_a_thing_key_must_be_one_clean_segment():
    lane = LivingLane()
    for bad in ("a/b", "a\\b", "a\nb", "a\x00b", "..", ".", "", "  ", "a​b"):
        with pytest.raises(ValueError):
            lane.remember(bad, "x")


def test_no_subject_id_appears_in_the_living_store_or_the_ledger(tmp_path, monkeypatch):
    """H-8's grep, made a test. A roster subject exists (so `subj-01` is a real id
    in the household); the operator keeps a living concern keyed by the *thing*; and
    the living store and its ledger carry no subject id at all — the lane never
    touches the roster, and its keys and audit ref the thing."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    child = Roster(Sidecar()).add(name="Synthetic Child", minor=True)
    assert str(child) == "subj-01"

    lane = LivingLane()
    lane.remember("growth", PRIOR)
    lane.remember("growth", LATEST)

    living_dir = tmp_path / "living"
    ledger_file = tmp_path / "logs" / "living.jsonl"
    for f in list(living_dir.rglob("*")) + [ledger_file]:
        if f.is_file():
            assert "subj-" not in f.read_text(encoding="utf-8", errors="ignore"), (
                f"a subject id reached the living lane via {f} (H-8)"
            )


# ── no egress at all ─────────────────────────────────────────────────────────


def test_the_lane_has_no_egress_path():
    """L5, and no way out. The module imports no export path, defines no export or
    serve function, and never calls one — the cell holds raw text that crosses no
    boundary, purposed or otherwise."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not any("export" in m for m in imported), f"the lane imports an egress path: {imported}"
    assert "homestead.keep.rungs" not in imported, "the lane serves nothing — it holds no Classified"

    banned_calls = {"serve", "serve_all", "export_record", "export_history", "export_card"}
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            called.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    assert not (banned_calls & called), f"the lane reaches an egress call: {banned_calls & called}"

    # And no export-shaped method on the class.
    assert not any("export" in n or "egress" in n for n in dir(LivingLane))
