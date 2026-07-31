"""sandbox_runner.py — D2's missing half: actually running a build inside Kart.

Everything else already built for the seam consumes a `Plan` that someone
handed it. Nothing PRODUCED one by running a build in isolation. This module
is that step, and only that step:

    BuildTask --> kartikeya.sandbox.run_shell(...) --> stdout --> Plan
                  (isolation)                                     (data)

and then it stops. `stores/seam.py`'s `cross()` is what decides whether the
returned Plan is allowed to cross — verify_manifest (D4), validate_plan (D3
scope), scan_plan (D3 content), the MCP allowlist (D5), then apply. None of
that is duplicated, reimplemented, or short-circuited here.

**This module makes no trust decision.** It answers one question — "did this
command run, in isolation, and what plan-shaped bytes did it print" — the
same question D2 says Kart is trusted to answer: *"Kart is trusted for
isolation, not for policy."* It has no idea whether a plan is allowed. It
never widens anything, never signs anything, never consults a keyring, and
never writes into `apps/`. Writing files is the seam's act, after every
check has passed; a runner that wrote them would be the sandbox writing at
host privilege, which is exactly what D3 exists to prevent.

Import-pure per D13: imports `kartikeya` (an adopted external dependency —
the design's own "Adopted dependencies: D2 → Kart") and this package's own
`plan`, and nothing from `safe-app-store` — not `stores/sap_gate.py`, not
`stores/seam.py`. The dependency direction stays host-imports-builder.

## What a "build task" is, in v1

Nothing in this codebase yet defines what "the model generates code" looks
like concretely (D7's vLLM/LiteLLM routing is undesigned code, not just
unwired). Rather than invent a model-facing protocol and pretend it's load
bearing, v1 defines the narrowest thing that is actually runnable today:

    A BuildTask is a shell command. It runs inside Kart. Its ENTIRE stdout
    must be exactly one JSON object in `plan.py`'s wire format. Anything a
    build wants to log goes to stderr.

Three deliberate calls in that sentence, each with the alternative it beat:

1. **stdout, not a file the seam picks up.** stdout is the narrowest
   channel out of a sandbox — a string, already returned by `run_shell`,
   requiring no shared writable bind mount between the sandbox and the
   store. The file-drop alternative needs exactly the kind of shared
   writable surface D3's diagram removes, and would make this module do
   filesystem I/O it has no business doing.

2. **The WHOLE of stdout, not "the last JSON-looking line."** Scanning
   output for something plan-shaped is shape-inference on untrusted output
   — the same fail-open reasoning D5 threw out when it replaced "anything
   shaped like read/propose passes through" with an explicit allowlist. A
   build that prints progress to stdout gets a hard error telling it to use
   stderr, not a parser guessing which line it meant.

3. **A shell command, not a model handle.** When D7's model routing exists,
   it produces one of these — the command becomes "run the generated
   builder"; nothing here changes. This is the seam-facing half, and it is
   honestly the only half that exists.

## The plain-fallback problem, handled loudly

`run_shell` reports `sandbox: "bwrap" | "plain" | "none"`. "plain" means
**no isolation happened at all** — the command ran as an ordinary subprocess
at this process's own privilege. Treating that as equivalent to "bwrap"
would make every D2 claim in this repo false in exactly the environments
where it matters.

So: `require_isolation=True` is the DEFAULT, and it is fail-closed like
every other stage in this pipeline. A caller who genuinely wants the dev
path must pass `require_isolation=False` explicitly, and what comes back is
marked: `SandboxRun.isolated is False`, a loud string in
`SandboxRun.warnings`, and a `logging.warning`. There is no code path where
"plain" silently reads as "bwrap".

Two real facts about kartikeya 0.0.7 this handling is built around, verified
against its installed code, not assumed:

- `run_shell` does **not** check whether `bwrap` is installed. `use_bwrap()`
  reports *intent* (true unless `WILLOW_KART_NO_BWRAP` is set), and on a
  host with no `bwrap` binary `run_shell` returns
  `{"returncode": -1, "error": "[Errno 2] ... 'bwrap'", "sandbox": "bwrap"}`
  — a result labelled `bwrap` that never entered a sandbox. `kartikeya`'s
  own `execute._run_one_shell` pre-flights `bwrap_available()` for this
  reason; so does this module, rather than trusting the `sandbox` label
  alone.
- `WILLOW_KART_NO_BWRAP` and `KART_SANDBOX_CONFIG` are read from
  `os.environ` **at call time**, not from `run_shell`'s `env=` argument
  (which only populates the child's environment). Forcing plain mode
  therefore requires a process-global env mutation — see `_scoped_env`,
  which does it in a restored, explicitly-named, non-thread-safe way rather
  than hiding it.

`kartikeya.sandbox.sandbox_manifest()` is deliberately NOT used for the
isolation verdict: its `engine` field is `"bwrap" if use_bwrap() else
"plain"` — intent again, not fact. The verdict here comes from the actual
run result cross-checked against `bwrap_available()`.

## What this module does NOT achieve (stated, not implied)

- **D6's per-build mount boundary is not enforced here.** D6 wants the bind
  mount restricted to exactly `apps/<builder_id>/<app_name>/`. Kart's binds
  come from its own `kart-sandbox.json` mount policy, not from `cwd` — a
  `workdir` narrows where the command *starts*, not what it can *reach*.
  The hook for closing this is `sandbox_config` (below), which points Kart
  at a caller-authored per-build policy; authoring that policy is real work
  that does not exist yet.
- **Concurrency.** `_scoped_env` is process-global. Two builds running
  concurrently in one process can interleave their env. D6's multi-builder
  concurrency needs a worker process per build, not this.
- **Nothing about the plan's trustworthiness.** A Plan returned from here
  is untrusted input that happens to be well-formed. The seam is what makes
  it anything more.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Iterator

from .plan import Plan, PlanError, plan_from_dict

_log = logging.getLogger("the_forge.sandbox_runner")

DEFAULT_TIMEOUT_S = 120

# A plan is a declaration, not a payload dump. Anything past this is either
# a bug or an attempt to make the host buffer something enormous. Honest
# limit: this is checked AFTER `run_shell` already read the whole stream
# into the parent's memory, so it bounds what gets *parsed*, not what gets
# *read* — `run_shell` gives no streaming hook to do better.
MAX_PLAN_STDOUT_BYTES = 1_000_000

_ISOLATION_BWRAP = "bwrap"


class SandboxError(Exception):
    """The build did not produce a usable plan — Kart missing, isolation
    unavailable when it was required, the command failed or timed out, or
    its stdout was not exactly one well-formed plan.

    Wraps `PlanError` the same way `stores/seam.py`'s `SeamError` does
    (`raise ... from e`), so one call site catches one exception type while
    the original cause stays on `__cause__`. Raising means nothing crossed
    and nothing was written — this module writes nothing in any case."""


# ── the build task ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class BuildTask:
    """One build, as v1 defines it (see module docstring).

    `builder_id` and `app_name` are carried, not enforced: their
    path-safety charset is checked where it actually matters —
    `sap_gate._check_builder_id` for the identity the gate verifies, and
    `plan.validate_plan` for the app_name the containment math uses. This
    module re-deriving those rules would be a second copy of a security
    check that could drift from the real one; a non-empty check is all it
    honestly needs to run a command.

    `allow_net` is the only network knob exposed, matching D7: network is a
    *declared* permission, off by default. Kart's `allow_localhost` and
    `allow_db` lanes exist but nothing in The Forge declares them, and a
    knob with no policy behind it is a widening waiting to be used.
    """

    builder_id: str
    app_name: str
    command: str
    workdir: str | None = None
    timeout_s: int = DEFAULT_TIMEOUT_S
    allow_net: bool = False

    def __post_init__(self) -> None:
        if not self.builder_id or not self.builder_id.strip():
            raise SandboxError("BuildTask has no builder_id")
        if not self.app_name or not self.app_name.strip():
            raise SandboxError("BuildTask has no app_name")
        if not self.command or not self.command.strip():
            # kart returns sandbox="none" for a blank command — a third
            # isolation value that means "nothing ran." Refuse up front so
            # that state never reaches the classifier.
            raise SandboxError("BuildTask has an empty command — nothing to run")
        if self.timeout_s <= 0:
            raise SandboxError(f"BuildTask timeout_s must be positive, got {self.timeout_s!r}")


@dataclasses.dataclass(frozen=True)
class SandboxRun:
    """The mechanics of one sandboxed execution — no plan, no judgement.

    `isolation` is the classified truth, not `run_shell`'s raw label:
      "bwrap"              — really sandboxed.
      "bwrap_setup_failed" — bwrap was invoked and never reached the
                             command (mount/namespace failure).
      "plain"              — NO isolation; ran as an ordinary subprocess.
      anything else        — kart reported something this module doesn't
                             recognize; treated as not-isolated.
    """

    command: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    isolation: str
    warnings: tuple[str, ...] = ()

    @property
    def isolated(self) -> bool:
        return self.isolation == _ISOLATION_BWRAP


@dataclasses.dataclass(frozen=True)
class BuildResult:
    """A well-formed plan plus the honest provenance of how it was produced.

    Hand `plan` to `stores/seam.py`'s `cross()`; hand `run` to whoever is
    recording what happened. `isolated` travels with the plan on purpose —
    a seam-side ledger (D10) that records a crossing without recording
    whether the build was actually contained is recording half a fact.
    """

    plan: Plan
    run: SandboxRun
    builder_id: str
    app_name: str

    @property
    def isolated(self) -> bool:
        return self.run.isolated

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.run.warnings


# ── plan parsing — pure, no sandbox needed ───────────────────────────────────

def parse_plan_stdout(stdout: str, *, expect_app_name: str | None = None) -> Plan:
    """Turn a sandboxed command's stdout into a `Plan`, or raise
    `SandboxError`.

    Strict by construction: the whole of `stdout` (stripped of surrounding
    whitespace) must be one JSON object in `plan.py`'s wire format. Not the
    last line, not the first `{...}` found — see the module docstring for
    why scanning for something plan-shaped is the wrong shape of check.

    `expect_app_name` catches a build emitting a plan for a different app
    than the one it was asked to build. That is a *consistency* check, not
    a security one, and it is the only place it can be made: the seam
    receives `app_name` from the plan itself and has no independent record
    of what was requested. It does NOT replace `validate_plan`'s charset
    and containment checks, which are still the thing standing between an
    app_name and the filesystem.

    Every failure mode here is a `SandboxError`, including the ones a naive
    parser would let escape as `json.JSONDecodeError`, `UnicodeDecodeError`,
    `AttributeError` (JSON `null`/list/number where an object was
    expected), or `PlanError`.
    """
    size = len(stdout.encode("utf-8", errors="replace"))
    if size > MAX_PLAN_STDOUT_BYTES:
        raise SandboxError(
            f"build printed {size} bytes to stdout, over the {MAX_PLAN_STDOUT_BYTES}-byte "
            f"plan limit — refusing to parse it as a plan"
        )

    text = stdout.strip()
    if not text:
        raise SandboxError(
            "build printed nothing to stdout — a build task must print exactly one "
            "plan-shaped JSON object there (logs go to stderr)"
        )

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        raise SandboxError(
            f"build stdout is not a single JSON document: {e} — a build task must print "
            f"exactly one plan-shaped JSON object to stdout and nothing else "
            f"(diagnostics belong on stderr)"
        ) from e

    if not isinstance(payload, dict):
        raise SandboxError(
            f"build stdout parsed as {type(payload).__name__}, not a JSON object — "
            f"a plan is an object with 'app_name' and 'entries'"
        )

    try:
        plan = plan_from_dict(payload)
    except PlanError as e:
        # Same wrap-and-preserve shape stores/seam.py uses for PlanError.
        raise SandboxError(f"build produced a malformed plan: {e}") from e
    except (TypeError, AttributeError) as e:
        # plan_from_dict indexes and iterates its input; a payload like
        # {"app_name": 1, "entries": 7} reaches it as a dict and fails
        # deeper in. A caller of this module should never see a raw
        # TypeError from someone else's stdout.
        raise SandboxError(f"build produced a malformed plan: {e!r}") from e

    if expect_app_name is not None and plan.app_name != expect_app_name:
        raise SandboxError(
            f"build was asked to build app_name={expect_app_name!r} but emitted a plan "
            f"for {plan.app_name!r} — refusing to forward a plan for a different app"
        )
    return plan


# ── isolation mechanics ──────────────────────────────────────────────────────

@contextlib.contextmanager
def _scoped_env(**overrides: str | None) -> Iterator[None]:
    """Set process-global env vars for the duration of a block, restoring
    exactly what was there before (including "was not set at all").

    Process-global and therefore NOT thread-safe, said plainly rather than
    discovered later: two concurrent `run_in_sandbox` calls in one process
    can interleave these. It exists because kartikeya reads
    `WILLOW_KART_NO_BWRAP` and `KART_SANDBOX_CONFIG` from `os.environ` at
    call time — `run_shell`'s `env=` argument only populates the CHILD's
    environment, so there is no per-call way to set them. D6's
    multiple-concurrent-builders requirement needs a process per build; it
    does not need this to become cleverer.
    """
    previous: dict[str, str | None] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _classify_isolation(result: dict) -> str:
    """The isolation verdict, derived from what actually happened rather
    than from the label kart attached. `sandbox_setup == "failed"` is
    kart's own `--json-status-fd` signal that bwrap exited before ever
    exec'ing the command — a bwrap-labelled result where no command ran
    inside anything."""
    label = result.get("sandbox")
    if label == _ISOLATION_BWRAP:
        if result.get("sandbox_setup") == "failed" or result.get("error") == "sandbox_setup_failed":
            return "bwrap_setup_failed"
        return _ISOLATION_BWRAP
    return str(label) if label else "unknown"


def _preflight_isolation(*, require_isolation: bool) -> tuple[bool, tuple[str, ...]]:
    """Decide, before running anything, whether real isolation is available.

    Returns `(force_plain, warnings)`. Raises `SandboxError` when isolation
    was required and cannot be delivered — fail-closed, matching every
    other stage of this pipeline.
    """
    from kartikeya.sandbox import bwrap_available, use_bwrap  # local: see run_in_sandbox

    intends = use_bwrap()
    available = bwrap_available()

    if intends and available:
        return False, ()

    if intends and not available:
        reason = (
            "bubblewrap is not installed on this host — kartikeya would report "
            "sandbox='bwrap' while failing to launch it at all (kartikeya 0.0.7 "
            "does not pre-check the binary inside run_shell)"
        )
    else:
        reason = "WILLOW_KART_NO_BWRAP is set — kartikeya's own sandboxing is switched off"

    if require_isolation:
        raise SandboxError(
            f"refusing to run a build without isolation: {reason}. "
            f"D2 makes Kart the thing that contains execution; running the command "
            f"anyway would be a build executing unsandboxed at host privilege. Pass "
            f"require_isolation=False only in a dev environment, and only knowing "
            f"the result is not sandboxed."
        )

    return (intends and not available), (
        f"NO ISOLATION: this build ran unsandboxed, as an ordinary subprocess at this "
        f"process's own privilege, because {reason}. require_isolation=False was passed "
        f"explicitly. This is NOT equivalent to bwrap isolation and no D2 claim holds "
        f"for this run.",
    )


def run_in_sandbox(task: BuildTask, *, require_isolation: bool = True,
                   sandbox_config: Path | None = None) -> SandboxRun:
    """Run `task.command` inside Kart and return the mechanics of that run.

    Does not parse a plan (see `run_build`), does not judge anything, and
    writes nothing to disk. Raises `SandboxError` if the command could not
    be run, was not isolated when isolation was required, timed out, or
    exited non-zero.

    `sandbox_config` points Kart at a caller-authored mount policy for the
    duration of this call (`$KART_SANDBOX_CONFIG`). It is the hook for
    D6's per-build bind boundary; this module does not author such a
    policy, and without one Kart uses whatever policy its own resolution
    order finds — which is NOT restricted to
    `apps/<builder_id>/<app_name>/`.
    """
    try:
        from kartikeya.sandbox import run_shell
    except ImportError as e:
        # Deliberately lazy. `stores/seam.py` puts apps/the-forge/src on
        # sys.path and imports `the_forge` without pip-installing it —
        # keeping this import inside the function means the plan schema and
        # the scan stay usable with zero third-party packages, and a
        # missing Kart surfaces as this module's own typed error rather
        # than an ImportError from an unrelated import line.
        raise SandboxError(
            "kartikeya is not installed — the sandbox runner cannot run a build without it "
            "(`pip install kartikeya`; declared in apps/the-forge/pyproject.toml)"
        ) from e

    if task.workdir is not None:
        # A read, not a write: this module never creates the working
        # directory. An absent cwd would otherwise surface from deep
        # inside run_shell as a generic returncode -1.
        if not Path(task.workdir).is_dir():
            raise SandboxError(f"workdir does not exist or is not a directory: {task.workdir!r}")

    if sandbox_config is not None and not Path(sandbox_config).is_file():
        # kartikeya's own resolve_sandbox_config() does NOT error on a
        # missing/unparseable $KART_SANDBOX_CONFIG — it silently falls
        # through to $WILLOW_HOME/kart-sandbox.json, then its vendored
        # default (verified against the installed kartikeya 0.0.7 source).
        # sandbox_config is named above as the hook for D6's per-build mount
        # boundary; a typo'd path here would silently swap the caller's
        # intended restriction for whatever fallback policy Kart resolves
        # to instead, unnoticed. Fail closed the same way workdir does,
        # rather than let policy silently widen.
        raise SandboxError(f"sandbox_config does not exist or is not a file: {sandbox_config!r}")

    force_plain, warnings = _preflight_isolation(require_isolation=require_isolation)
    for w in warnings:
        _log.warning("%s", w)

    env_overrides: dict[str, str | None] = {}
    if force_plain:
        env_overrides["WILLOW_KART_NO_BWRAP"] = "1"
    if sandbox_config is not None:
        env_overrides["KART_SANDBOX_CONFIG"] = str(sandbox_config)

    with _scoped_env(**env_overrides):
        result = run_shell(
            task.command,
            timeout=task.timeout_s,
            allow_net=task.allow_net,
            cwd=task.workdir,
        )

    isolation = _classify_isolation(result)
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    run = SandboxRun(
        command=task.command,
        returncode=int(result.get("returncode", -1)),
        stdout=stdout,
        stderr=stderr,
        elapsed_s=float(result.get("elapsed_s", 0.0)),
        isolation=isolation,
        warnings=warnings,
    )

    # Re-check after the fact, not just before: the pre-flight reasons about
    # the host, this reasons about what the run actually reported. A bwrap
    # setup failure is only visible here.
    if require_isolation and not run.isolated:
        raise SandboxError(
            f"build did not run isolated: kart reported isolation={isolation!r} "
            f"(stderr: {_clip(stderr)})"
        )

    if result.get("error") == "timeout":
        raise SandboxError(
            f"build timed out after {task.timeout_s}s (isolation={isolation!r}); "
            f"partial stderr: {_clip(stderr)}"
        )
    if run.returncode != 0:
        raise SandboxError(
            f"build command failed with returncode {run.returncode} "
            f"(isolation={isolation!r}, error={result.get('error')!r}); "
            f"stderr: {_clip(stderr)}"
        )
    return run


def run_build(task: BuildTask, *, require_isolation: bool = True,
              sandbox_config: Path | None = None) -> BuildResult:
    """Run a build inside Kart and return the `Plan` it printed.

    The whole of D2's orchestration, in one call: isolate, run, read one
    plan-shaped JSON object off stdout, hand it back. What happens to that
    plan next is `stores/seam.py`'s decision, not this module's — nothing
    here has been authorized, signed, scanned, scope-checked, or written.
    """
    run = run_in_sandbox(task, require_isolation=require_isolation, sandbox_config=sandbox_config)
    plan = parse_plan_stdout(run.stdout, expect_app_name=task.app_name)
    return BuildResult(plan=plan, run=run, builder_id=task.builder_id, app_name=task.app_name)


def _clip(text: str, limit: int = 800) -> str:
    """Keep an error message readable when a failing build dumps a wall of
    stderr. Marks the cut rather than truncating silently — same reasoning
    as kartikeya's own `clip_output`."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[{len(text) - limit} chars clipped]"
