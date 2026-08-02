"""SHA256-verified install into Waydroid, with the outcome written down.

Two things this module deliberately does not do.

It does not download. The APK is a file an operator already put on disk; the
digest in the catalog is checked against that file. Fetching would make this app
a client of exactly the kind of ranked, ad-funded distribution surface it exists
to stand in for.

It does not raise on failure as its primary channel. A grant that failed to
install and a grant that installed cleanly are different facts, and the second
one must not be the default reading just because nobody caught an exception.
Every path through `perform()` returns a result and every result gets written to
the disposition log by the caller.

What verification here does and does not cover: the digest proves the bytes on
disk are the bytes the operator recorded. It says nothing about what those bytes
do at move five. That is what the interruption record is for, and the two are
separate on purpose — provenance and behaviour are different claims and a store
that conflates them is the reason this app exists.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ADB = "adb"
INSTALL_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str


def digest(path: Path, chunk: int = 1 << 20) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            sha.update(block)
    return sha.hexdigest()


def verify(path: Path, expected: str) -> Result:
    if not expected:
        return Result(False, "catalog entry has no sha256; refusing to install unverified bytes")
    if not path.exists():
        return Result(False, f"apk not found at {path}")
    actual = digest(path)
    if actual != expected.lower():
        return Result(False, f"sha256 mismatch: expected {expected}, file is {actual}")
    return Result(True, f"sha256 {actual} verified")


def perform(apk_path: Path, expected_sha256: str, *, runner=None) -> Result:
    """Verify then install. Never raises for an expected failure mode.

    `runner` is injectable so the tests can drive the failure paths — a missing
    adb, a non-zero exit, a timeout — without a device or a Waydroid session.
    It defaults to `None` rather than to `subprocess.run` so the lookup happens
    at call time: a default bound at import time cannot be patched, and a test
    that thinks it has replaced the runner but has not is worse than no test.
    """
    runner = runner or subprocess.run
    checked = verify(apk_path, expected_sha256)
    if not checked.ok:
        return checked

    if shutil.which(ADB) is None:
        return Result(False, "adb not on PATH; is Waydroid installed and running?")

    try:
        completed = runner(
            [ADB, "install", "-r", str(apk_path)],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return Result(False, f"adb install timed out after {INSTALL_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return Result(False, f"could not run adb: {exc}")

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip() or "(no stderr)"
        return Result(False, f"adb exit {completed.returncode}: {stderr}")

    stdout = (completed.stdout or "").strip()
    if "Success" not in stdout:
        # adb has historically exited 0 while printing a failure. Trusting the
        # exit code alone is how a failed install gets logged as a success.
        return Result(False, f"adb exit 0 but output was: {stdout or '(empty)'}")

    return Result(True, f"{checked.detail}; adb reported success")
