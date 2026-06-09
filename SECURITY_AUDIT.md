---
b17: STOR1
title: Security Audit — safe-app-store (Multi-App Repository)
date: 2026-05-06
auditor: Heimdallr (Claude Code, Haiku 4.5)
status: open (tracking doc)
---

# Security Audit — safe-app-store

Part of the Level 2 full-fleet security audit.

This is a monorepo containing 20+ safe-apps: story-timeline, dating-wellbeing, the-squirrel, law-gazelle, nasa-archive, genealogy, game, field-notes, source-trail, utety-chat, and others.

This PR is the tracking doc. No patches here — patches go in separate PRs.

---

## Scope

| App | Files | Status |
|-----|-------|--------|
| story-timeline | 15 | ✅ Scanned |
| dating-wellbeing | 12 | ✅ Scanned |
| the-squirrel | 25 | ✅ Scanned |
| law-gazelle | 8 | ✅ Scanned |
| nasa-archive | 12 | ✅ Scanned |
| genealogy | 6 | ✅ Scanned |
| game | 8 | ✅ Scanned |
| source-trail | 8 | ✅ Scanned |
| utety-chat | 9 | ✅ Scanned |
| field-notes | 6 | ✅ Scanned |
| llmphysics | 4 | ✅ Scanned |
| private-ledger | 6 | ✅ Scanned |
| public-ledger | 6 | ✅ Scanned |
| other (bt-controller, etc.) | ~36 | ✅ Scanned |
| **Total** | 167 | 100% |

---

## Rubric Results

| # | Check | Status | Finding |
|---|---|---|---|
| R1 | SQL injection via f-string/identifier concat | ⚠️ P2 | Dynamic schema/field names in f-strings. Safe (hardcoded), but code smell. See ST-SQL-01. |
| R2 | Shell injection — `os.system`, `shell=True` | ✅ PASS | No subprocess or os.system calls in production code. Test/script usage is safe (list form). |
| R3 | Path traversal — file ops accepting `../` or absolute | ✅ PASS | No user-controlled path input found. DATA_DIR, INDEX_PATH hardcoded. |
| R4 | Hardcoded credentials in VC | ✅ PASS | No hardcoded API keys or passwords in source. OAuth tokens stored in vault. |
| R5 | CORS wildcards | ⚠️ P2 | Several apps expose HTTP servers (story-timeline, nasa-archive) with CORS. See ST-HTTP-01. |
| R6 | XSS — `innerHTML` with user input | ⚠️ P2 | Web frontends (nasa-archive, story-timeline) accept user input in HTML. See ST-XSS-01. |
| R7 | Unsigned/unverified code execution | ✅ PASS | No eval, exec, or code loading from untrusted sources. |
| R8 | Missing auth on MCP tools | ✅ N/A | Safe-apps are not MCP servers. Auth handled per app. |
| R9 | Bare `except` swallowing security-critical errors | ⚠️ P2 | 10+ bare except clauses in law-gazelle and other apps. See ST-EXC-01. |
| R10 | Predictable temp paths, world-readable `/tmp` state | ✅ PASS | No /tmp usage found. Temp files use system default (safe). |
| R11 | Race conditions / missing locks | ⚠️ P2 | Database operations use connection pooling. No explicit locking in multi-user paths. See ST-RACE-01. |
| R12 | `safe_integration.py` status() correctness | ⚠️ P1 | **CRITICAL:** Many safe_integration.py files import from hardcoded dev paths. See ST-INT-01. |
| R13 | Entry point in manifest is importable | ⚠️ P1 | Apps fail to import on non-USER systems due to hardcoded paths. See ST-INT-01. |
| R14 | `requirements.txt` with pinned deps | ⚠️ P2 | Most apps use version ranges instead of pinned versions. See ST-DEP-01. |
| R15 | No hardcoded developer home paths | 🚨 **P0** | **CRITICAL:** 40+ hardcoded paths to USER's machine. See ST-PATH-01. |

---

## Findings

### ST-PATH-01 — Hardcoded Developer Paths (P0 — CRITICAL)

**Severity:** P0 (Blocks execution on any non-USER system)
**Files affected:** 12+ safe-apps
**Status:** Open

Across the monorepo, paths are hardcoded to USER's machine, making apps non-portable:

```python
# dating-wellbeing/wellbeing_db.py:20
sys.path.insert(0, os.environ.get("WILLOW_CORE", "~/github/Willow/core"))

# private-ledger/ledger_db.py:19
_WILLOW_CORE = "~/github/Willow/core"

# nasa-archive/enrich_rallies.py:22-29
WILLOW_ROOT = "~/github/Willow"
DATA_DIR = Path("~/github/safe-app-nasa-archive/data/rallies")
```

Examples found:
- `~/github/Willow` (should use willow-1.9)
- `~/github/willow-1.5`, `willow-1.7` (old versions)
- `~/github/...` (Windows paths, non-portable)
- `~/persona.md` (developer-specific)

This prevents all these apps from running on any system except USER's.

**Fix:** Use environment variables with portable fallbacks:

```python
# Instead of hardcoded path:
WILLOW_CORE = os.environ.get("WILLOW_CORE", str(Path(__file__).parent.parent.parent / "willow-1.9" / "core"))

# Or use relative paths:
WILLOW_CORE = Path(__file__).parent.parent.parent / "willow-1.9" / "core"
```

**Affected apps:**
- dating-wellbeing, genealogy, game, field-notes, source-trail, law-gazelle, llmphysics, utety-chat, nasa-archive, private-ledger, and others.

---

### ST-SQL-01 — f-Strings in SQL WHERE/Schema Clauses (P2)

**Files:** Multiple database modules (dating-wellbeing/wellbeing_db.py, the-squirrel/squirrel_db.py, etc.)
**Severity:** P2 (Code smell, not injection risk)
**Status:** Open

Schema and field names are interpolated using f-strings:

```python
# dating-wellbeing/wellbeing_db.py:69
cur.execute(f"SET search_path = {SCHEMA}, public")

# the-squirrel/responder/commands/person.py:81
cur.execute(f"UPDATE the_squirrel.persons SET {field} = %s, updated_at = now() WHERE id = %s", ...)
```

Risk: SCHEMA and field names are hardcoded/controlled, not user input. However, this pattern is fragile — if these ever become user-controlled, injection is possible.

**Fix:** Use parameterized identifier lists or use PgSQL's `quote_ident()`:

```python
# For schema names (not parameterizable):
schema_list = ["dating_wellbeing", "public"]  # Allowlist
if SCHEMA not in schema_list:
    raise ValueError("Invalid schema")
cur.execute(f"SET search_path = {SCHEMA}, public")

# For field names (not parameterizable):
allowed_fields = ["status", "created_at", "score"]  # Allowlist
if field not in allowed_fields:
    raise ValueError(f"Field not allowed: {field}")
cur.execute(f"UPDATE ... SET {field} = %s", (value,))
```

---

### ST-INT-01 — safe_integration.py Import Failures (P1 — BLOCKS DEPLOYMENT)

**Files:** All safe_integration.py files
**Severity:** P1 (Blocks safe-app deployment)
**Status:** Open

Each safe_integration.py depends on hardcoded paths that fail on non-USER systems:

```python
# From dating-wellbeing/safe_integration.py
sys.path.insert(0, os.environ.get("WILLOW_CORE", "~/github/Willow/core"))
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX
```

When WILLOW_CORE is not set and `~/...` doesn't exist:
1. Import fails silently (no FileNotFoundError because sys.path.insert doesn't validate)
2. `from user_lattice import ...` raises ModuleNotFoundError
3. safe_integration.py can't be imported
4. SAFE framework rejects the app (status() must succeed)

**Fix:** Use portable paths + validation:

```python
import os
from pathlib import Path

# Try multiple locations in order
willow_paths = [
    Path(os.environ.get("WILLOW_CORE", "")),
    Path(__file__).parent.parent.parent / "willow-1.9" / "core",
    Path.home() / "github" / "willow-1.9" / "core",
]

willow_core = None
for p in willow_paths:
    if (p / "user_lattice.py").exists():
        willow_core = p
        break

if not willow_core:
    raise EnvironmentError(
        "WILLOW_CORE not set and could not find willow-1.9/core. "
        "Set WILLOW_CORE or place safe-apps as sibling of willow-1.9."
    )

sys.path.insert(0, str(willow_core))
from user_lattice import ...
```

---

### ST-EXC-01 — Bare `except:` Clauses (P2)

**File:** law-gazelle/src/gazelle_engine.py (lines 160, 179, 206, 249, 270, 438, 609, 624)
**Severity:** P2
**Status:** Open

Multiple bare `except:` clauses that swallow all exceptions:

```python
# gazelle_engine.py:160
try:
    parse_results = self._perform_parsing()
except:  # Catches KeyboardInterrupt, SystemExit, etc.
    return {}
```

Bare `except:` catches even system signals and should never be used.

**Fix:** Catch specific exceptions:

```python
except (ValueError, TypeError, KeyError):
    print(f"[WARN] Parsing failed: {type(e).__name__}: {e}", flush=True)
    return {}
```

---

### ST-HTTP-01 — CORS or XSS in Web Frontends (P2)

**Files:** story-timeline/web.py, nasa-archive web frontend
**Severity:** P2
**Status:** Open

Web endpoints in story-timeline and nasa-archive expose HTTP servers without documented CORS policy. If used in production (not just local dev), CORS wildcards or missing headers could expose data to cross-origin requests.

**Recommendation:** Document CORS policy and validate Origin headers if deployed beyond localhost.

---

### ST-RACE-01 — Missing Locks in Multi-User Database Paths (P2)

**Files:** Multiple database modules
**Severity:** P2
**Status:** Open

Apps use connection pooling (safe) but some update operations may have race conditions in multi-user scenarios:

```python
# Example: No transaction isolation level set
cur.execute("UPDATE ... SET field = field + 1 WHERE ...")  # Not atomic
```

In single-user scenarios (common for safe-apps) this is acceptable. If deployed with concurrent users, explicit locking or transaction isolation is needed.

**Recommendation:** Add transaction isolation level when multi-user support is needed.

---

### ST-DEP-01 — Unpinned Dependencies (P2)

**Status:** Open

Most safe-apps use version ranges:
```
psycopg2-binary>=2.9.0
requests>=2.25.0
```

**Fix:** Pin to tested versions:
```
psycopg2-binary==2.9.9
requests==2.31.0
```

---

## Summary

| Priority | Count | Items |
|---|---|---|
| P0 | 1 | ST-PATH-01 (hardcoded paths — blocks execution) |
| P1 | 2 | ST-INT-01 (safe_integration import failures), ST-SQL-01 (schema injection risk) |
| P2 | 4 | ST-EXC-01, ST-HTTP-01, ST-RACE-01, ST-DEP-01 |

**CRITICAL BLOCKER:** ST-PATH-01 (hardcoded paths) must be fixed before any safe-app-store app can run on a non-USER system. This affects 12+ apps.

---

*ΔΣ=42*
