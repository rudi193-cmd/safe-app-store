# Convention: `--web` and `--serve` — the two non-TUI surfaces
b17: SAPS1

Every SAFE app has one primary surface (the TUI, `make run app=<name>`). Two
optional flags expose the *same data* to two *different consumers*. This
document fixes what they mean, because right now they don't agree.

## The rule (one sentence each)

- **`--web` is for the user.** A human-facing, **read-only** HTML mirror of the
  app's data, served on `127.0.0.1` only. You open it in a browser to *look*.
- **`--serve` is for a model.** A machine-facing **stdio JSON** interface a
  model/agent drives programmatically. **Read-only by default**; writes are
  opt-in behind `--allow-write`.

> Audience is the whole distinction: `--web` renders for eyes, `--serve` speaks
> JSON for an agent. A flag that starts an HTTP API "for a model" is still the
> wrong flag — that's a web server, and its audience is ambiguous. Keep the two
> surfaces on the two flags.

Neither flag may make a network request off `127.0.0.1`. Both are covered by the
store-wide `tests/test_no_egress.py` AST scan.

## Canonical implementation (private-ledger)

private-ledger is the reference. Routing lives in `main()`; each surface is
**lazy-imported** so the default TUI path never pulls in `http.server` or the
serve seam:

```python
def main():
    import sys
    argv = sys.argv[1:]

    if "--serve" in argv:                    # machine: stdio JSON for a model
        allow_write = "--allow-write" in argv
        from . import serve                   # lazy import
        serve.run(allow_write=allow_write)
        return

    if "--web" in argv:                      # human: read-only HTML mirror
        port = 8770
        if "--port" in argv:
            try:
                port = int(argv[argv.index("--port") + 1])
            except (IndexError, ValueError):
                port = 8770
        from . import web                     # lazy import
        web.serve(port=port)
        return

    LedgerApp().run()                        # default: the TUI
```

`dev.sh` forwards `"$@"` to `python -m <package>`, so `./dev.sh --web`,
`./dev.sh --serve`, and `./dev.sh --serve --allow-write` all work.

### Contract checklist for an app adopting the flags

- [ ] `--web` binds `127.0.0.1` only, serves read-only HTML, default port in the
      app's own range, `--port N` override.
- [ ] `--serve` speaks newline-delimited JSON on stdio, read-only unless
      `--allow-write` is passed.
- [ ] Both surfaces are **lazy-imported** from `main()` — importing the app for
      the TUI must not import the web/serve machinery.
- [ ] `dev.sh` documents all three invocations in its header and forwards `"$@"`.
- [ ] `tests/test_no_egress.py` present and green (see convention #13).
- [ ] README "Run" section lists: default TUI, `--web`, `--serve`
      (+ `--allow-write`).

## Current state across the store (the reason this doc exists)

`--serve` means three contradictory things today. This table is the migration
target, not the current reality.

| App | Today | Verdict | Required change |
|---|---|---|---|
| **private-ledger** | `--web` = HTML mirror; `--serve` = stdio JSON (+`--allow-write`) | ✅ canonical | none — this is the reference |
| **public-ledger** | `--serve` = "Start FastAPI server" (a human web server) | ❌ wrong audience | that surface is human → rename to `--web`; add a real stdio `--serve` for agents (or drop it) |
| **oakenscrolls-office** | `--serve` **aliases** `--web` → both launch the web mirror | ❌ direct opposite | drop the `--serve` alias; `--web` only, unless a genuine stdio agent surface is added |
| **ask-jeles** | `--serve` = FastAPI verification **API** | ⚠️ HTTP-for-machines | either expose the verify surface over stdio as `--serve`, or name the HTTP API explicitly and free `--serve` for the stdio contract |

The naming collision is exactly the kind of "same word, three meanings" drift
Loki's semantic Mistletoe is meant to catch. Until each app is migrated, an
agent cannot rely on `--serve` doing the same thing twice — which defeats the
point of a machine flag.

## Adoption is incremental

This doc standardizes the *convention*; the per-app refactors (public-ledger,
oakenscrolls-office, ask-jeles) are follow-on work, each a small PR that moves
one app onto the reference shape and updates its README + `dev.sh`. Do them one
at a time; keep `tests/test_no_egress.py` green through each.

---

*Convention doc. Reference implementation: `apps/private-ledger`. Companion to
convention #13 (shared `_lib` + no-egress test). `ΔΣ=42`*
