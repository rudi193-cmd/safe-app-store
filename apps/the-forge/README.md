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

## Tests

```bash
cd apps/the-forge
python -m pip install -e ".[dev]"
pytest -q
```

The sandbox-runner tests make real (unmocked) kartikeya calls. On a host
without bubblewrap they exercise Kart's documented **plain** fallback — real
subprocesses, real timeouts, but **no isolation** — and the one test that
needs genuine bwrap containment skips itself rather than pretending. See
`tests/test_sandbox_runner.py`'s module docstring.
