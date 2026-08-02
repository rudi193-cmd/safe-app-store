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
