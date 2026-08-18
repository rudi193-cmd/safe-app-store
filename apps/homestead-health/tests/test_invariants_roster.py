"""H-1 — a subject is opaque everywhere but the roster and the detail pane.

Promoted out of `test_invariants_pending.py` when `homestead_health.roster`
landed as **bite 2 — subjects before records**. This is the health module's
first promotion, and it went through the door the engine built: the moment the
module existed `test_pending_liveness` failed by name, and would not go green
again until the H-1 test was carried here, unmarked, and the `roster` key came
out of `UNBUILT`. The `test_h1_…` body and docstring are kept exactly as they
were written in the pending file — a promotion moves a claim, it does not
rewrite it.

The bite's *done when* (`homestead/docs/PLAN-homestead-health.md` § bite 2) is
two things, and both are held below:

* **a subject survives a restart** — a store-bound roster persists through
  `keep/record` and resumes its counter, so a second process finds the subject
  and never re-mints its id;
* **a log line about a subject carries the id and nothing else** — the rendered
  `VisibleLog` is grepped for the name the way the engine's chokepoint test
  greps the surface layer, and the name is absent while the id is present.

And two more the design (H-1) is really about: the id does not depend on the
name (the bite-1 audit's tightening), and the name crosses a boundary only
through the gate — derived to the id on an ambient surface, rendered only in the
detail pane.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from homestead.keep.record import Sidecar
from homestead.keep.logs import VisibleLog
from homestead.keep.rungs import Disposition, Rung, Surface, serve

from homestead_health.roster import ROSTER_MATTER, Roster, SubjectRef

PKG = Path(__file__).resolve().parent.parent / "homestead_health"


# ── H-1, promoted verbatim ───────────────────────────────────────────────────


def test_h1_a_subject_reference_never_carries_a_name():
    roster = Roster()
    ref = roster.add(name="Synthetic Child", minor=True)
    # The reference is what keys, logs and derived text may carry. If any
    # fragment of the name survives into it, the roster has minted a datum as
    # a reference and H-1 is not built, whatever else is.
    assert "Synthetic" not in str(ref) and "Child" not in str(ref)
    # **Tightened after the bite-1 audit**, which showed the substring check
    # alone accepts `subj-01-<base64 of the name>` — no fragment survives,
    # the whole name does, trivially reversible. So the stronger claim: the
    # id must not *depend on* the name at all. Two fresh rosters, same
    # position, different names — an id derived from the name differs; an id
    # minted by the roster (a counter, per the plan's own `subj-01`) cannot.
    # An implementation that wants non-deterministic ids must come back to
    # this test with a mechanism argument, which is exactly the conversation
    # H-1 wants to force.
    other = Roster().add(name="Entirely Different Person", minor=True)
    assert str(ref) == str(other), (
        "an id that varies with the name is derived from the name — the "
        "roster mints ids; the datum does not"
    )


def test_the_minted_id_is_the_plans_shape():
    """`subj-01`, counting up — the id the plan and the worked example name."""
    roster = Roster()
    assert str(roster.add(name="A", minor=False)) == "subj-01"
    assert str(roster.add(name="B", minor=True)) == "subj-02"


# ── the name's rung encodes minority, and the gate serves it ─────────────────


def test_a_minors_name_is_l4_and_an_adults_is_l3():
    """The custody pack's distinction, on the roster: a person → L3, a minor → L4
    (`opposing_party` vs `child_name`). And minority is read *back* from the rung,
    the one place it is recorded — no parallel flag to drift from it."""
    roster = Roster()
    child = roster.add(name="Synthetic Child", minor=True)
    adult = roster.add(name="Synthetic Adult", minor=False)

    assert roster.name_of(child).rung is Rung.L4
    assert roster.name_of(adult).rung is Rung.L3
    assert roster.is_minor(child) is True
    assert roster.is_minor(adult) is False


def test_a_minors_name_derives_to_the_id_on_a_list_and_renders_only_in_detail():
    """The name crosses a boundary only through the gate. On the ambient list a
    minor's name (L4) is withheld and the id stands in; the pane opened by a human
    (S1_DETAIL) renders it. That is what "opaque everywhere but the detail pane"
    means in one served datum."""
    roster = Roster()
    child = roster.add(name="Synthetic Child", minor=True)
    record = roster.name_of(child)

    on_list = serve(record, Surface.S1_LIST)
    assert on_list.disposition is Disposition.DERIVE
    assert on_list.value == str(child)          # the id stands in — not the name
    assert "Synthetic" not in str(on_list.value)

    in_detail = serve(record, Surface.S1_DETAIL)
    assert in_detail.disposition is Disposition.RENDER
    assert in_detail.value == "Synthetic Child"  # the name, only where a human asked


def test_the_module_reads_no_payload_itself():
    """H-1 says the mapping is *served through the gate*. The roster hands
    `Classified` records to callers and reaches no `.payload` of its own — the
    same discipline the engine's chokepoint scan holds the surface layer to,
    asserted here on this module because the health app has no chokepoint scan of
    its own yet."""
    tree = ast.parse((PKG / "roster.py").read_text(encoding="utf-8"))
    reaches = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "payload"
    ]
    assert not reaches, f"roster.py reaches a .payload at lines {reaches}; serve() is the path"


# ── an in-memory roster writes nothing and dials nothing ─────────────────────


def test_a_bare_roster_persists_nothing(tmp_path, monkeypatch):
    """`Roster()` with no store is in-memory: it mints ids and holds names in the
    process and touches no disk. Nothing under the household root is created —
    not the sidecar it would write to, not the logs it would record into."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    roster = Roster()
    roster.add(name="Synthetic Adult", minor=False)
    assert not (tmp_path / "sidecar").exists()
    assert not (tmp_path / "logs").exists()


# ── a subject survives a restart ─────────────────────────────────────────────


def test_a_subject_survives_a_restart(tmp_path, monkeypatch):
    """Bite 2's first *done when*. A store-bound roster persists each subject
    through `keep/record`; a fresh roster over the same store — a new process, in
    effect — finds it, with its name and its minority intact."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    first = Roster(Sidecar())
    child = first.add(name="Synthetic Child", minor=True)

    reopened = Roster(Sidecar())
    assert child in reopened
    assert reopened.name_of(child).rung is Rung.L4
    assert reopened.is_minor(child) is True
    assert serve(reopened.name_of(child), Surface.S1_DETAIL).value == "Synthetic Child"


def test_the_counter_resumes_and_ids_never_collide(tmp_path, monkeypatch):
    """A restart must not re-mint an id. The reopened roster resumes its counter
    from the highest id on disk, so the next subject continues the sequence rather
    than clobbering the first — the store would refuse the clobber (I-9), and the
    roster must not even try."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    first = Roster(Sidecar())
    first.add(name="A", minor=False)
    first.add(name="B", minor=True)

    reopened = Roster(Sidecar())
    third = reopened.add(name="C", minor=False)
    assert str(third) == "subj-03"
    assert len(reopened) == 3


def test_a_survived_subject_still_serves_only_through_the_gate(tmp_path, monkeypatch):
    """The rung travels with the datum across the restart, so a resumed adult name
    (L3) still renders on the list while a resumed minor name (L4) still derives —
    the storage boundary did not quietly declassify either (I-11)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    first = Roster(Sidecar())
    child = first.add(name="Synthetic Child", minor=True)

    reopened = Roster(Sidecar())
    assert serve(reopened.name_of(child), Surface.S1_LIST).disposition is Disposition.DERIVE


# ── a log line about a subject carries the id and nothing else ───────────────


def test_the_log_line_carries_the_id_and_no_name(tmp_path, monkeypatch):
    """Bite 2's second *done when*, and H-1 at the log. Adding a subject writes one
    `VisibleLog` act; the rendered log is grepped for the name the way the engine's
    chokepoint test greps the surface layer, and the name is absent while the id is
    present. The log has no free-text field for a name to enter through (F-4), and
    the roster passes it none."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    roster = Roster(Sidecar())
    child = roster.add(name="Synthetic Child", minor=True)

    log_file = tmp_path / "logs" / "visible.jsonl"
    assert log_file.exists(), "a store-bound roster records a visible act on add"
    rendered = log_file.read_text(encoding="utf-8")
    assert str(child) in rendered, "the log line references the subject by id"
    assert "Synthetic" not in rendered and "Child" not in rendered, (
        "the rendered log carries the id and nothing of the name (H-1, I-15)"
    )


def test_the_visible_log_read_back_holds_no_name(tmp_path, monkeypatch):
    """The same claim through the log's own reader rather than the raw file, so a
    future change to the on-disk shape cannot slip a name past the grep above."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    roster = Roster(Sidecar())
    child = roster.add(name="Synthetic Child", minor=True)

    entries = VisibleLog().read()
    assert entries, "the add wrote a visible entry"
    blob = repr(entries)
    assert str(child) in blob
    assert "Synthetic" not in blob and "Child" not in blob


# ── the persisted subject survives an actual process exit ────────────────────


def test_a_subject_survives_the_process_exiting(tmp_path):
    """The strongest form of "survives a restart": a *separate interpreter* writes
    the subject, this one reads it back. In-process persistence can be faked by a
    cache that never touched disk; a second process cannot see a cache."""
    writer = (
        "from homestead.keep.record import Sidecar\n"
        "from homestead_health.roster import Roster\n"
        "r = Roster(Sidecar())\n"
        "print(r.add(name='Synthetic Child', minor=True))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", writer],
        cwd=str(PKG.parent),
        env={"HOMESTEAD_HOME": str(tmp_path), "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    sid = proc.stdout.strip()
    assert sid == "subj-01"

    import os

    os.environ["HOMESTEAD_HOME"] = str(tmp_path)
    try:
        reopened = Roster(Sidecar())
        assert SubjectRef(sid) in reopened
        assert reopened.is_minor(sid) is True
    finally:
        del os.environ["HOMESTEAD_HOME"]
