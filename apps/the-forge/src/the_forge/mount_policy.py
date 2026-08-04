"""mount_policy.py — D6's per-build mount boundary, closed.

`sandbox_runner.py`'s own module docstring names the gap plainly: *"D6's
per-build mount boundary is not enforced here... Kart's binds come from its
own kart-sandbox.json mount policy, not from cwd."* Verified against the
installed dependency, not assumed — `kartikeya`'s vendored default policy
(`kartikeya/data/kart-sandbox.json`) ships:

    "bind_read_write": ["{{WILLOW_ROOT}}", "{{HOME}}/.willow", "{{HOME}}/.local"]

`{{WILLOW_ROOT}}` is this repo — `safe-app-store` itself. Without an
override, every build's sandbox gets **read-write** access to the whole
store, every other builder's `apps/<builder_id>/<app_name>/` included. D6
says the bind mount "is restricted to exactly" one builder's own app
directory. This module is what makes that true: it generates a
kart-sandbox.json-shaped policy whose `bind_read_write` is exactly one path,
and nothing wider, then hands it to `sandbox_runner.run_in_sandbox`'s
existing `sandbox_config` hook via `run_scoped_build` below.

## What actually goes in the generated policy, and why

`bind_read_write` — exactly `[<apps_root>/<builder_id>/<app_name>]`. Nothing
else. Never `{{WILLOW_ROOT}}`, never the repo root, never a second entry.
This is the entire point of the module; every test in the companion test
file pins it.

`bind_read_only` — kept to the vendored default's `/usr`, `/etc`, `/sys`
only. A build needs a working OS userland to run an interpreter at all;
those three don't name anything builder- or repo-specific. Deliberately
**dropped** from the vendored default:

  - `{{HOME}}/github` — on this fleet's layout (docs/fleet_paths.md),
    `~/github/safe-app-store` *is* `{{WILLOW_ROOT}}`, and `apps/` lives
    inside it. Read-only is still "reachable": binding this would let a
    build list and read every other builder's `apps/<builder_id>/<app_name>/`
    tree, plus the rest of the store's source. Exactly the leak D6 exists
    to prevent, just with `ro` instead of `rw` in front of it.
  - `{{HOME}}/.config/git`, `{{HOME}}/.config/systemd` — host-operator
    config, not needed to execute arbitrary generated code, and no
    upside to widening the surface for something unused.

`bind_try` — best-effort binds kartikeya silently skips if the path is
absent (`_add(..., required=False)`), kept to the entries that are generic
OS/runtime plumbing rather than anything HOME- or repo-scoped: `/run/user`,
`/run/media`, `{{XDG_RUNTIME_DIR}}`, `/run/systemd/resolve`. Dropped:
every `{{HOME}}/...` entry in the vendored default (`.gitconfig`, `.npmrc`,
`.cargo`, `.npm`, package-manager caches, `{{WILLOW_ROOT}}/.venv-dev`) —
none of them are needed to *run* code, only to *install* it, and installing
is a network operation gated by D7's declared `allow_net`, a separate
concern from this module's one job. `bind_try_read_only` keeps the
vendored default's `/lib32` unchanged — a merged-usr compatibility symlink
target, not HOME- or repo-scoped either way.

`worktree_scan_roots` — explicitly set to `[]`, not left absent. Absent
falls back to kartikeya's own default, `["{{WILLOW_ROOT}}/worktrees"]`, and
`collect_bind_mounts` adds anything discovered there as a **read-write**
bind (`_discover_worktree_targets` → `_add(wt, False)`) — a second, silent
way `bind_read_write` could stop being exactly one path. Silence here is
not neutral; it has to be turned off explicitly.

`env_prefixes` / `credential_env_prefixes` / `db_env_prefixes` are
deliberately **absent** from the generated policy, not zeroed. Absent means
kartikeya's own `kart_env()` falls back to its module-level hardcoded
defaults (`cfg.get(...) or _DEFAULT_CREDENTIAL_PREFIXES`, etc.) — this
module's job is the D6 *mount* boundary; env-var gating is D7's declared-
network concern and already has its own fail-closed default one layer down,
independent of what this file does or doesn't set.

## What this module does NOT close (stated, not implied)

`collect_bind_mounts` (kartikeya, not this module) makes a handful of
**unconditional** additions that no caller-supplied policy can turn off:
Python venv candidates, `psycopg2`'s install dir, `sysconfig`'s `purelib`,
and (in `build_bwrap_argv`) the `~/.willow` trust-root read-only overlay and
merged-usr `/bin`→`/usr/bin`-style symlinks. All read-only, all interpreter/
runtime plumbing rather than a builder's own tree — but they are kartikeya's
behavior, not something a `kart-sandbox.json` can restrict, and this module
does not attempt to.

Import-pure per D13: stdlib + this package's own `sandbox_runner` module.
Nothing from `safe-app-store`.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .sandbox_runner import BuildResult, BuildTask, run_build

# Same charset rule this repo already enforces everywhere a string becomes a
# filesystem path component: stores/promote_check.py's _APP_ID_PATTERN,
# stores/sap_gate.py's _BUILDER_ID_PATTERN, the_forge/plan.py's
# _APP_NAME_PATTERN. One rule, reused again rather than reinvented — see
# plan.py's own note on why an unvalidated path component is a real
# traversal hole, not a hypothetical one.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# The read-only surface kept from kartikeya's vendored default — see the
# module docstring for what was dropped and why.
_BASE_RO_BINDS = ["/usr", "/etc", "/sys"]
_BASE_TRY_BINDS = ["/run/user", "/run/media", "{{XDG_RUNTIME_DIR}}", "/run/systemd/resolve"]
_BASE_TRY_RO_BINDS = ["/lib32"]


class MountPolicyError(Exception):
    """`builder_id`/`app_name` failed the path-safety charset, or the
    resulting scoped path failed to resolve strictly inside `apps_root`.
    Raised before any path is built from the untrusted value and before any
    file is written — fail-closed, same shape as `plan.PlanError` and
    `sandbox_runner.SandboxError`."""


def _check_id(label: str, value: str) -> str:
    """Validate one path component BEFORE it touches a `Path(...)` call.

    Order matters here: every caller in this module runs this first, so a
    hostile `builder_id`/`app_name` — `"../../etc"`, an absolute path, an
    embedded null byte, an empty string — is refused here, not downstream
    where it would already be part of a path or a written file. The pattern
    itself rules out traversal and absolute paths structurally: the first
    character must be alphanumeric, so neither `.` (a leading `..`) nor `/`
    (an absolute path) can start a valid value, and no charset character
    admits a null byte.
    """
    if not isinstance(value, str) or not value or not _ID_PATTERN.match(value):
        raise MountPolicyError(
            f"{label} {value!r} fails the path-safety charset "
            f"(^[A-Za-z0-9][A-Za-z0-9_.-]*$, same rule as promote_check.py's "
            f"_APP_ID_PATTERN / sap_gate.py's _BUILDER_ID_PATTERN / "
            f"plan.py's _APP_NAME_PATTERN) — refusing before any path or "
            f"mount policy is built from it"
        )
    return value


def _scoped_app_root(builder_id: str, app_name: str, apps_root: Path) -> Path:
    """Resolve `apps_root/builder_id/app_name`, refusing anything that
    doesn't land strictly inside `apps_root` after validation.

    The charset check in `_check_id` already makes traversal structurally
    impossible for `builder_id`/`app_name` alone (neither `..` nor `/` can
    appear). This containment re-check is defense in depth against the one
    thing the charset can't rule out — `apps_root` itself resolving through
    a symlink into somewhere unexpected — the same belt-and-suspenders shape
    `plan.py`'s `_contain_file_write` uses for the same reason.
    """
    _check_id("builder_id", builder_id)
    _check_id("app_name", app_name)
    root = Path(apps_root).resolve()
    scoped = (root / builder_id / app_name).resolve()
    if scoped == root or not scoped.is_relative_to(root):
        raise MountPolicyError(
            f"scoped path {scoped} for builder_id={builder_id!r} "
            f"app_name={app_name!r} does not resolve strictly inside "
            f"apps_root={root} — refusing to build a mount policy for a "
            f"path that doesn't stay inside its own tree"
        )
    return scoped


def build_scoped_policy(builder_id: str, app_name: str, apps_root: Path) -> dict:
    """Return a kart-sandbox.json-shaped policy dict scoped to exactly one
    build's app directory. Raises `MountPolicyError` for a hostile/invalid
    `builder_id` or `app_name` before any path is built.

    `bind_read_write` is a one-element list: `apps_root/builder_id/app_name`
    — never `{{WILLOW_ROOT}}`, never the repo root, never anything wider.
    See the module docstring for every other key's reasoning.
    """
    scoped_root = _scoped_app_root(builder_id, app_name, apps_root)
    return {
        "version": 1,
        "description": (
            f"The Forge D6 scoped mount policy — generated for "
            f"builder_id={builder_id!r} app_name={app_name!r} by "
            f"the_forge.mount_policy.build_scoped_policy. Not hand-authored; "
            f"do not reuse this file across builds or builders."
        ),
        "bind_read_only": list(_BASE_RO_BINDS),
        "bind_read_write": [str(scoped_root)],
        "bind_try": list(_BASE_TRY_BINDS),
        "bind_try_read_only": list(_BASE_TRY_RO_BINDS),
        # Explicitly empty — see module docstring. Absent would silently
        # fall back to kartikeya's own ["{{WILLOW_ROOT}}/worktrees"] default,
        # which can add a second, undeclared read-write bind.
        "worktree_scan_roots": [],
    }


def write_scoped_policy(builder_id: str, app_name: str, apps_root: Path, *, dir: Path | None = None) -> Path:
    """Build the scoped policy and write it to a fresh temp file, returning
    its `Path`. Validation happens inside `build_scoped_policy`, before this
    function ever calls `tempfile.mkstemp` — a hostile `builder_id`/
    `app_name` raises `MountPolicyError` and leaves no file behind.

    A temp file matches `sandbox_config`'s existing call-scoped lifetime in
    `sandbox_runner.run_in_sandbox` (`$KART_SANDBOX_CONFIG` is read for the
    duration of one call, via `_scoped_env`) — this is not a policy meant to
    outlive the build it was generated for.
    """
    policy = build_scoped_policy(builder_id, app_name, apps_root)

    fd, name = tempfile.mkstemp(
        prefix="the-forge-kart-sandbox-", suffix=".json",
        dir=str(dir) if dir is not None else None,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(policy, f, indent=2)
            f.write("\n")
    except BaseException:
        # Best-effort: don't leave a half-written policy file behind on a
        # write failure (disk full, permissions) — same fail-closed spirit
        # as every other stage here, applied to our own tempfile.
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
    return Path(name)


def run_scoped_build(
    task: BuildTask,
    apps_root: Path,
    *,
    require_isolation: bool = True,
) -> BuildResult:
    """Run `task` through `sandbox_runner.run_build`, scoped to exactly its
    own `apps_root/task.builder_id/task.app_name` bind — the piece that
    actually closes D6's gap for a caller that uses it.

    A helper nobody calls doesn't count: this is that call site. As of this
    change, nothing outside this module's own tests invokes
    `run_scoped_build` — no CLI subcommand, no seam wiring, nothing in
    `stores/` reaches it (and per D13, nothing here could reach `stores/`
    either way). Wiring an actual build entry point to call this instead of
    the unscoped `run_build` is the next step, not this one; see
    `apps/the-forge/README.md` and `cli.py`'s `_STATUS` for the honest
    current state.

    Builds the policy, runs the build, and removes the temp policy file
    afterward regardless of outcome — the policy is call-scoped, not meant
    to survive past the one build it was generated for.
    """
    policy_path = write_scoped_policy(task.builder_id, task.app_name, apps_root)
    try:
        return run_build(task, require_isolation=require_isolation, sandbox_config=policy_path)
    finally:
        try:
            policy_path.unlink()
        except OSError:
            pass
