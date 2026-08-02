"""Break each mechanism on purpose and require the suite to notice.

A gate that has never been observed failing is a decoration. band-camp-arcade's
`npm run test:mutations` is the store's worked example of this; these are the
same idea in pytest.

Each case copies the app to a temp directory, applies one source edit that
disables one mechanism, and runs *only* the test that claims to cover it. The
assertion is that the run fails. A mutation that leaves the suite green means
the mechanism is unguarded, whatever the file says about it.

The `named_test` in each case is deliberately specific rather than the whole
suite: it checks that the intended test is the one doing the catching, not some
unrelated assertion tripping over the same edit.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]

Case = tuple[str, str, str, str, str]

MUTATIONS: "list[Case]" = [
    (
        "a stale measurement stops demoting",
        "playgate/interruption.py",
        'if installed_version is None or installed_version == self.observed_version:',
        'if True:',
        "tests/test_interruption.py::test_a_measurement_demotes_when_the_build_moves_under_it",
    ),
    (
        "a missing record quietly becomes assumed",
        "playgate/interruption.py",
        '        if raw is None:\n            raise InterruptionError(',
        '        if raw is None:\n            return cls(provenance="assumed")\n        if False:\n            raise InterruptionError(',
        "tests/test_interruption.py::test_a_missing_record_is_an_error_not_an_assumed_one",
    ),
    (
        "combination averages instead of taking the floor",
        "playgate/interruption.py",
        'return min(states, key=PROVENANCE_ORDER.index)',
        'return max(states, key=PROVENANCE_ORDER.index)',
        "tests/test_interruption.py::test_a_view_is_worth_its_weakest_input",
    ),
    (
        "a grant no longer needs a reason",
        "playgate/disposition.py",
        'if not reason.strip():',
        'if False:',
        "tests/test_disposition.py::test_a_reason_is_required_to_grant_as_well",
    ),
    (
        "the log lets an answered request be answered again",
        "playgate/disposition.py",
        'if current["disposition"] != OPEN:',
        'if False:',
        "tests/test_disposition.py::test_answering_twice_is_refused",
    ),
    (
        "adb's exit code is trusted over its output",
        "playgate/install.py",
        'if "Success" not in stdout:',
        'if False:',
        "tests/test_install.py::test_a_zero_exit_without_success_is_still_a_failure",
    ),
    (
        "a digest mismatch no longer blocks the install",
        "playgate/install.py",
        '    if not checked.ok:\n        return checked',
        '    if False:\n        return checked',
        "tests/test_install.py::test_perform_never_installs_unverified_bytes",
    ),
    (
        "the server will bind any interface",
        "playgate/server.py",
        'if host not in ("127.0.0.1", "::1", "localhost"):',
        'if False:',
        "tests/test_no_egress.py::test_serve_refuses_a_non_loopback_bind",
    ),
    (
        "the catalog accepts an entry with nothing recorded",
        "playgate/catalog.py",
        'interruption = Interruption.from_json(entry.get("interruption"))',
        'interruption = Interruption.from_json(entry.get("interruption") or {"provenance": "assumed"})',
        "tests/test_catalog.py::test_an_entry_with_no_interruption_field_is_refused",
    ),
    (
        "the log defaults back into the app's own directory",
        "playgate/paths.py",
        'return _vp.resolve(APP_ID, "requests.jsonl", env_vars=("PLAYGATE_LOG",))',
        'return Path(__file__).resolve().parents[1] / "data" / "requests.jsonl"',
        "tests/test_paths.py::test_the_log_does_not_default_into_the_app_directory",
    ),
    (
        "an unconfigured host searches its own install directory for APKs",
        "playgate/server.py",
        '    apk_root: "Path | None" = None',
        '    apk_root: "Path | None" = APP_ROOT',
        "tests/test_paths.py::test_an_unconfigured_host_refuses_to_install_rather_than_searching_itself",
    ),
]


def _mutate(tmp_path: Path, relative: str, find: str, replace: str) -> Path:
    workdir = tmp_path / "app"
    shutil.copytree(APP, workdir, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    target = workdir / relative
    source = target.read_text()
    assert find in source, (
        f"mutation anchor not found in {relative}; the source moved and this "
        f"mutation is now testing nothing:\n  {find!r}"
    )
    target.write_text(source.replace(find, replace, 1))
    return workdir


@pytest.mark.parametrize(
    "description,relative,find,replace,named_test",
    MUTATIONS,
    ids=[case[0] for case in MUTATIONS],
)
def test_the_gate_catches_the_mutation(tmp_path, description, relative, find,
                                       replace, named_test):
    workdir = _mutate(tmp_path, relative, find, replace)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", named_test, "-x", "-q", "-p", "no:cacheprovider"],
        cwd=workdir, capture_output=True, text=True, timeout=300,
    )
    assert completed.returncode != 0, (
        f"mutation '{description}' left {named_test} passing — the mechanism is "
        f"unguarded\n{completed.stdout[-2000:]}"
    )


def test_the_unmutated_suite_passes_in_a_copy(tmp_path):
    """The control.

    Without this, every mutation above could be 'caught' by a copy that was
    broken for some unrelated reason, and the whole file would prove nothing.
    """
    workdir = tmp_path / "app"
    shutil.copytree(APP, workdir, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider",
         "--deselect", "tests/test_mutations.py"],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert completed.returncode == 0, completed.stdout[-3000:]
