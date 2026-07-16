# The Squirrel — sixty-second walkthrough

Cold start to family tree, one command at a time. Everything below runs
offline on a fresh machine; the only requirements are Python 3.10+ and
`pip install -r requirements.txt`.

## 1 · Open the door

    python3 squirrel_app.py

`http://localhost:8425` — the journal. The box (`~/.squirrel`) is
provisioned on first boot: database, vault, gate ledger, receipts.

## 2 · Meet a family (optional)

    @squirrel: demo load

Nine fictional Acorns arrive. Look around: **People** (cameo grid),
**Tree** (pedigree, three generations), **Stash** (family rumors,
confidence-graded).

## 3 · Plant your own

    @squirrel: add person Hazel Acorn b.1902 d.1988 p.Cedar_Grove
    @squirrel: add person Alder Acorn b.1874
    @squirrel: link Hazel Acorn → parent → Alder Acorn
    @squirrel: tree Hazel Acorn

## 4 · Stash what you half-know

    @squirrel: stash "Hazel kept letters in a biscuit tin" --confidence uncertain
    @squirrel: show stash
    @squirrel: bind fragment 1 → Hazel Acorn

Fragments are the squirrel's stash: raw observations, graded
confirmed / likely / uncertain / speculative, promoted to the tree
when they've earned it.

## 5 · Find where to dig

    @squirrel: find sources Iowa 1880s
    @squirrel: search findagrave Hazel Acorn

779 community archives indexed locally. Results are links — nothing
leaves this machine unless you click one.

## 6 · Invite the librarian (optional)

Slide the header toggle to **Chat** (needs a local Ollama):

    Who in my tree was born before 1880?

Jeles reads, never writes, can never export. The gate enforces that,
not etiquette.

## 7 · Check the trail

    @squirrel: status
    @squirrel: receipts

Or the **Privacy** page: the ONLINE switch, the AI's mode, everything
that's been touched in plain sentences, and GO QUIET.

## 8 · Take it with you

    @squirrel: export gedcom

Standard GEDCOM 5.5.1 on your Desktop. Any genealogy tool reads it.
Cleanup: `@squirrel: demo clear`. Total exit: delete `~/.squirrel`.

ΔΣ=42
