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

`status` is the only real thing here right now — it says what's designed
vs. what's actually implemented (nothing beyond this skeleton, yet).

## Tests

```bash
cd apps/the-forge
python -m pip install -e ".[dev]"
pytest -q
```
