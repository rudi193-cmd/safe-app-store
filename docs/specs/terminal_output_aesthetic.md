# Terminal Output Aesthetic — SAFE App Platform Standard
**Date:** 2026-05-06 | **Status:** Draft | **b17:** TOAS1

## Purpose

SAFE apps run in diverse environments: terminal, IDE, systemd, web dashboard. Consistent terminal output aesthetic ensures users can quickly parse app state, understand errors, and trace execution flow across the platform.

This spec defines the standard for text output from any SAFE app invoked via `make run app=<name>` or direct CLI.

---

## Core Principles

1. **Scannable** — Users should grasp output state in <100ms of glance
2. **Self-describing** — Every line is clear without context
3. **Machine-readable where it counts** — Errors/status codes parseable, not just human prose
4. **Quiet by default** — Only output what's necessary; silence is success
5. **Fail visibly** — Errors must stand out; warnings must warn; success must confirm

---

## Message Categories

### Success ✓
Indicates operation completed without error. Keep these brief.

```
✓ file written: /home/user/output.json
✓ database migrated (2 tables, 450 rows)
✓ 3 tests passed
```

**Format:** `✓ <brief summary>` or no output at all if the result speaks for itself.

### Error ✗
Operation failed. User action may be required. Always include:
- What failed
- Why it failed (if non-obvious)
- What the user can do about it

```
✗ permission denied: /data/protected.db — check file permissions (chmod 644)
✗ connection timeout: postgres://localhost:5432 — is the server running?
✗ invalid app_id: "my-app@invalid" — app_id must match ^[a-zA-Z0-9][a-zA-Z0-9_\-]*$
```

**Format:** `✗ <what failed>: <why> — <what to do>`

**Special case — exit with code:** If fatal, exit 1 after printing error. Parser scripts depend on exit codes.

### Warning ⚠
Operation succeeded but with caveats. User may want to know.

```
⚠ deprecated: manifest.permissions field is legacy — use manifest.permissions_v2
⚠ slow query: took 45s — consider adding an index on (user_id, created_at)
⚠ 50 records dropped: duplicates detected — review them at /tmp/duplicates.jsonl
```

**Format:** `⚠ <condition> — <context or recommendation>`

### Info ℹ
Non-critical status. Use sparingly; most apps output too much info.

```
ℹ loading plugins from ~/.safe/plugins/ — 3 found
ℹ run time: 2.34s
```

**Format:** `ℹ <status>`

### Progress (long operations only)
For operations >2 seconds, show progress. Apps with <2s runtime skip this.

```
→ scanning files... 45/1000
→ uploading... 234 MB / 500 MB
```

or multi-line:

```
[stage 1/4] analyzing...
[stage 2/4] transforming...
[stage 3/4] validating...
[stage 4/4] writing...
✓ done (3.2s)
```

**Format:** `→ <action>... <progress>` or `[<stage>] <action>`

---

## Formatting Standards

### Spacing
- One blank line between logical sections
- No double-blank lines
- Indent nested messages with 2 spaces

### Line length
- Aim for <100 chars; hard limit 120 (accessibility: terminal at 80 cols is rare but respected)
- Long paths/values: wrap after 80 chars with leading spaces for continuation

### Color (optional, no requirement)
Apps may use color for visual hierarchy:
- **Red** for errors (✗)
- **Yellow/Orange** for warnings (⚠)
- **Green** for success (✓)
- **Blue/Cyan** for info/progress (ℹ/→)

If no color: rely on emoji + text only. Colors are **optional** — must be readable without them.

### Emoji (required for status clarity)
Always include status emoji for:
- ✓ Success
- ✗ Error
- ⚠ Warning
- ℹ Info
- → Progress

No "dancing" animations or distracting spinners — they break log readability and fail in systemd/CI.

---

## Examples

### Minimal success (ideal)
```
$ make run app=story-timeline
✓ story-timeline is running at http://localhost:3000
```

### With progress (>5s operation)
```
$ make run app=binder process=scan
→ scanning files... 234/1000
→ scanning files... 500/1000
→ scanning files... 1000/1000
→ classifying... 45%
→ classifying... 100%
✓ scan complete: 1000 files, 234 tagged, 766 untagged (3.2s)
```

### Error with recovery hint
```
$ make run app=willow-nest intake
✗ drop zone not found: /home/user/Desktop/Nest
→ creating drop zone...
✓ /home/user/Desktop/Nest created
→ ready for intake (no files present yet)
```

### Multi-stage operation with warnings
```
$ make run app=compost files=~/Desktop/docs/
[1/4] reading... ✓ 12 files
[2/4] summarizing... ✓ 12 summaries  ⚠ 2 summaries incomplete (content >6000 chars)
[3/4] storing... ✓ 12 atoms ingested
[4/4] cleanup... ✓
✓ done (45.2s)
```

---

## What NOT to do

- ❌ "DEBUG:", "INFO:", "TRACE:" prefixes — use emoji instead
- ❌ Timestamps (systemd/logging handles this)
- ❌ PID or process ID (systemd handles this)
- ❌ Empty output on success (silent is fine, but explicit ✓ is better)
- ❌ Stack traces in user-facing output (log them, show a short error)
- ❌ Progress bars that overwrite previous lines (confuses logging; use staged output instead)
- ❌ Colors without emoji fallback (colorblind/no-color flags may disable color)
- ❌ Excessive output (>10 lines for a simple operation is too much)

---

## Integration Points

### `make run app=<name>`
Respected by Makefile infrastructure. Output goes to stdout; errors to stderr (exit 1).

### Systemd services
Services using `ExecStart=python3 app.py` capture stdout/stderr to journal. Keep output minimal; structured logging (JSON to file) is better for detailed diagnostic data.

### IDE / Claude Code
Terminal output is syntax-highlighted in some IDEs. Stick to plain text + emoji; avoid ANSI escape codes unless testing specifically for IDE support.

### Log files
Apps writing to `~/.willow/app.log` or similar should use structured format (JSON Lines, not pretty-printed). This spec is for **terminal output only**.

---

## Checklist for App Authors

- [ ] Success path outputs `✓ <summary>` or silent
- [ ] Errors output `✗ <what>: <why> — <fix>` and exit 1
- [ ] Warnings output `⚠ <condition> — <context>` (non-fatal)
- [ ] Long operations (>2s) show progress without overwriting
- [ ] Output <100 chars per line (aim for 80)
- [ ] No timestamps, PIDs, or DEBUG prefixes in user output
- [ ] Emoji used consistently (✓ ✗ ⚠ ℹ →)
- [ ] Color is optional; output is readable without it
- [ ] Tested in systemd logging (journal output is clean)

---

## Rationale: "The Obstacle Was Configuration"

SAFE apps succeed when users understand their state at a glance. Aesthetic consistency across the platform means:
- Users learn once, understand everywhere
- Error messages are trustworthy (formatted = reviewed)
- Logs are scannable
- Platform cohesion signals maturity

Configuration (how output looks) removes the barrier to comprehension. This spec is that configuration.

---

ΔΣ=42
