"""Install verification, and the failure paths that must not read as success."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from playgate import install


class Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def apk(tmp_path) -> Path:
    path = tmp_path / "game.apk"
    path.write_bytes(b"not really an apk, but it has a digest")
    return path


def test_digest_matches_hashlib(apk):
    import hashlib
    assert install.digest(apk) == hashlib.sha256(apk.read_bytes()).hexdigest()


def test_verify_accepts_the_recorded_digest(apk):
    assert install.verify(apk, install.digest(apk)).ok


def test_verify_is_case_insensitive_about_the_recorded_digest(apk):
    assert install.verify(apk, install.digest(apk).upper()).ok


def test_verify_rejects_a_mismatch(apk):
    result = install.verify(apk, "00" * 32)
    assert not result.ok and "mismatch" in result.detail


def test_verify_refuses_an_entry_with_no_digest(apk):
    """Not "install anyway and note it" — refuse. An unverified install is the
    thing the digest exists to prevent."""
    result = install.verify(apk, "")
    assert not result.ok and "unverified" in result.detail


def test_verify_reports_a_missing_file(tmp_path):
    result = install.verify(tmp_path / "absent.apk", "00" * 32)
    assert not result.ok and "not found" in result.detail


def test_perform_never_installs_unverified_bytes(apk, monkeypatch):
    """The ordering matters: a mismatch must short-circuit before adb is ever
    reached, so a bad digest cannot install on a machine where adb is present.
    """
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")

    def explode(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("adb was invoked on a digest mismatch")

    result = install.perform(apk, "00" * 32, runner=explode)
    assert not result.ok and "mismatch" in result.detail


def test_perform_reports_a_missing_adb(apk, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda _: None)
    result = install.perform(apk, install.digest(apk), runner=None)
    assert not result.ok and "adb not on PATH" in result.detail


def test_perform_succeeds_when_adb_says_success(apk, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")
    result = install.perform(
        apk, install.digest(apk), runner=lambda *a, **k: Completed(0, "Success\n")
    )
    assert result.ok and "adb reported success" in result.detail


def test_a_zero_exit_without_success_is_still_a_failure(apk, monkeypatch):
    """adb has historically exited 0 while printing a failure. Trusting the exit
    code alone is how a failed install gets logged as a successful one."""
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")
    result = install.perform(
        apk, install.digest(apk),
        runner=lambda *a, **k: Completed(0, "Failure [INSTALL_FAILED_INVALID_APK]"),
    )
    assert not result.ok and "INSTALL_FAILED_INVALID_APK" in result.detail


def test_a_nonzero_exit_reports_stderr(apk, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")
    result = install.perform(
        apk, install.digest(apk),
        runner=lambda *a, **k: Completed(1, "", "device offline"),
    )
    assert not result.ok and "device offline" in result.detail


def test_a_timeout_is_reported_not_raised(apk, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="adb", timeout=install.INSTALL_TIMEOUT_SECONDS)

    result = install.perform(apk, install.digest(apk), runner=slow)
    assert not result.ok and "timed out" in result.detail


def test_an_os_error_is_reported_not_raised(apk, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")

    def broken(*args, **kwargs):
        raise OSError("exec format error")

    result = install.perform(apk, install.digest(apk), runner=broken)
    assert not result.ok and "exec format error" in result.detail


# ---------------------------------------------------------------------------
# The real subprocess path
#
# Every test above injects a runner, which is right for driving failure modes
# but means `subprocess.run` itself — the argv, capture_output, text, timeout —
# is never executed by the suite. A typo in that argv list would pass all of
# them. These tests put a stub `adb` on PATH and call perform() with NO runner,
# so the call actually happens. No device and no Waydroid required, which is
# what makes them runnable in CI; what they cannot tell you is whether the
# thing on the other end is the child's tablet (see test_argv_names_no_device).
# ---------------------------------------------------------------------------

@pytest.fixture()
def stub_adb(tmp_path, monkeypatch):
    """An executable named `adb` on PATH that records its argv.

    Written against sys.executable rather than /bin/sh so the stub does not
    depend on a shell being present or on how it quotes.
    """
    import os
    import sys

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "argv.txt"

    def build(*, exit_code: int = 0, stdout: str = "Success",
              stderr: str = "", sleep: float = 0.0) -> Path:
        script = bin_dir / "adb"
        script.write_text(
            f"#!{sys.executable}\n"
            "import sys, time\n"
            f"open({str(calls)!r}, 'a').write(repr(sys.argv[1:]) + chr(10))\n"
            f"time.sleep({sleep})\n"
            f"sys.stdout.write({stdout!r})\n"
            f"sys.stderr.write({stderr!r})\n"
            f"sys.exit({exit_code})\n"
        )
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        return calls

    return build


def test_the_real_adb_call_succeeds_end_to_end(apk, stub_adb):
    calls = stub_adb()
    result = install.perform(apk, install.digest(apk))     # no runner injected
    assert result.ok, result.detail
    assert "adb reported success" in result.detail
    assert calls.exists(), "adb was never actually executed"


def test_argv_names_no_device(apk, stub_adb):
    """Locks the command as it is actually issued.

    It is `adb install -r <apk>` with **no device selector**. That is worth
    pinning rather than leaving implicit: with exactly one device attached, adb
    installs to whichever one that is, so on a host where Waydroid is not the
    only adb target the bytes can land somewhere else entirely and still report
    success. This test does not claim that is correct — it makes any change to
    the target visible in a diff instead of silent.
    """
    import ast

    calls = stub_adb()
    install.perform(apk, install.digest(apk))
    # literal_eval, not eval: test_no_dynamic_execution only scans playgate/,
    # so nothing here would have caught it — which is the reason to not write
    # it rather than a reason it is fine.
    assert ast.literal_eval(calls.read_text().strip()) == ["install", "-r", str(apk)]


def test_a_real_nonzero_exit_is_reported_not_raised(apk, stub_adb):
    stub_adb(exit_code=1, stdout="", stderr="error: no devices/emulators found")
    result = install.perform(apk, install.digest(apk))
    assert result.ok is False
    assert "adb exit 1" in result.detail
    assert "no devices/emulators found" in result.detail


def test_a_real_zero_exit_without_success_is_still_a_failure(apk, stub_adb):
    # adb has historically exited 0 while printing a failure. Proven here
    # against a real process, not a stand-in object.
    stub_adb(exit_code=0, stdout="Performing Streamed Install\nFailure [INSTALL_FAILED]")
    result = install.perform(apk, install.digest(apk))
    assert result.ok is False
    assert "INSTALL_FAILED" in result.detail


def test_a_real_timeout_is_reported_not_raised(apk, stub_adb, monkeypatch):
    # The genuine subprocess.TimeoutExpired path, with a real process killed.
    monkeypatch.setattr(install, "INSTALL_TIMEOUT_SECONDS", 1)
    stub_adb(sleep=30)
    result = install.perform(apk, install.digest(apk))
    assert result.ok is False
    assert "timed out after 1s" in result.detail


def test_unverified_bytes_never_reach_a_real_adb(apk, stub_adb):
    # The ordering that matters most: a digest mismatch must stop before the
    # process is spawned at all, not be caught after.
    calls = stub_adb()
    result = install.perform(apk, "0" * 64)
    assert result.ok is False
    assert "sha256 mismatch" in result.detail
    assert not calls.exists(), "adb ran despite an unverified digest"
