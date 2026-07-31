# The Forge

SAFE-native, multi-tenant app-building playground — the "10,000 other
app-building sites" pitch, wearing the store's consent/gate/promotion
mentality instead of instant deploy.

**Status: design-phase scaffold.** This directory is a package skeleton, not
a working builder. The actual architecture — trust model, sandboxing, the
signing gate, tenancy, the learning layer — lives in
[`docs/design/the-forge.md`](../../docs/design/the-forge.md) (13 decisions,
two independent reviews folded in). Read that first; this README won't stay
in sync with it by hand.

## Why a scaffold now, with so little built

Per the design's D13: this is built to leave `apps/` and become its own
repo, the way Nestor and Jeles already did. That means the core has to be
import-pure from the first commit, not retrofitted right before promotion —
`src/the_forge/` never imports `safe-app-store` internals, and nothing
outside it should need to import back in, once there's something worth
importing.

## Running it

```bash
cd apps/the-forge
python -m pip install -e .
the-forge status
```

or, via the store's own convention:

```bash
make run app=the-forge
```

`the-forge status` is the honest inventory — what's designed vs. what's
actually implemented. `the-forge plan-check` validates a plan against D3's
schema and content scan.

## D2 — running a build inside Kart

`src/the_forge/sandbox_runner.py` is the one piece that *executes* anything:
it runs a build command inside [kartikeya](https://pypi.org/project/kartikeya/)'s
bubblewrap sandbox and parses one plan-shaped JSON object off its stdout,
producing a `Plan` for `stores/seam.py cross` to judge. Per D2, Kart is
trusted for isolation and never for policy — the runner decides nothing,
writes nothing, and does not import the gate or the seam.

**It requires bubblewrap.** With no `bwrap` on the host it refuses by
default rather than running a build unsandboxed; `require_isolation=False`
is an explicit dev opt-out whose result is marked unisolated and logged as
such. Nothing yet *produces* a build command — D7's model routing and code
generation don't exist, so a build task is currently something a caller
writes by hand.

## D6 — the per-build mount boundary

`sandbox_runner.py`'s own docstring used to say plainly that D6's mount
boundary wasn't enforced: Kart's bind mounts come from its own
`kart-sandbox.json` policy, not from a build's working directory, and
without an override its vendored default binds `{{WILLOW_ROOT}}` —
`safe-app-store` itself — **read-write**, into every build's sandbox.
`src/the_forge/mount_policy.py` closes that gap: given a `builder_id` and
`app_name` (validated first, against the same
`^[A-Za-z0-9][A-Za-z0-9_.-]*$` charset used everywhere else in this repo for
a path component), it generates a policy whose `bind_read_write` is exactly
`apps/<builder_id>/<app_name>/` — never `WILLOW_ROOT`, never the repo root
— writes it to a call-scoped temp file, and hands it to
`sandbox_runner.run_in_sandbox` via the `sandbox_config` hook that was
already there waiting for it.

`run_scoped_build(task, apps_root, ...)` is the call site that actually
uses this — it builds the scoped policy from `task.builder_id`/
`task.app_name`, runs the build through it, and removes the temp policy
file afterward. **Said plainly, not implied**: nothing outside
`tests/test_mount_policy.py` calls `run_scoped_build` yet. There is no CLI
subcommand and no seam wiring pointed at it — the boundary exists and is
tested end to end (including a real round-trip through
`kartikeya.sandbox.load_sandbox_config` — deliberately not
`resolve_sandbox_config`, which exists only in an editable checkout this
environment happens to also carry, not in the actual published
`kartikeya>=0.0.7` this package depends on and installs; found in review,
2026-08-02), but no production build path takes it yet. A few of
kartikeya's own bind-mount additions — unconditional
Python venv/`psycopg2`/site-packages binds in `collect_bind_mounts`, the
`~/.willow` trust-root overlay in `build_bwrap_argv` — are not driven by
any caller-supplied policy at all, so this module can't narrow them either;
see its module docstring for the full accounting of what is and isn't
closed.

## Tests

```bash
cd apps/the-forge
python -m pip install -e ".[dev]"
pytest -q
```

The sandbox-runner and mount-policy tests make real (unmocked) kartikeya
calls. On a host without bubblewrap they exercise Kart's documented
**plain** fallback — real subprocesses, real timeouts, but **no
isolation** — and the one test that needs genuine bwrap containment skips
itself rather than pretending. See `tests/test_sandbox_runner.py`'s and
`tests/test_mount_policy.py`'s module docstrings.
