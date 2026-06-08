---
b17: 4NCC6
title: Security Audit — safe-app-the-squirrel
date: 2026-04-08
updated: 2026-04-15
auditor: Hanuman (Claude Code, Sonnet 4.6)
status: closed — all findings resolved
---

# Security Audit — safe-app-the-squirrel

Part of the Level 2 full-fleet security audit. See `agents/hanuman/projects/LEVEL2_AUDIT_PLAN.md` (b17: 379L3).

## Rubric Results

| # | Check | Status | Notes |
|---|---|---|---|
| R1 | SQL injection | ✅ PASS | All queries parameterized (`%s`). f-string `SET search_path = {SCHEMA}` uses hardcoded constant. |
| R2 | Shell injection | ✅ PASS | No shell execution |
| R3 | Path traversal | ✅ PASS | `_resolve_host()` WSL shim removed 2026-04-15; now uses Unix socket via `_default_dsn()`. No file reads at runtime. |
| R4 | Hardcoded credentials | ✅ PASS | None found |
| R5 | CORS wildcard | ✅ N/A | No HTTP server |
| R6 | XSS | ✅ PASS | web/index.html added 2026-04-15. All user input through `escHtml()`. External links via `encodeURIComponent`. |
| R7 | Unsigned code execution | ✅ PASS | None |
| R8 | Missing auth on APIs | ✅ N/A | No API server |
| R9 | Bare except swallowing errors | ✅ PASS | None critical |
| R10 | Predictable temp paths | ✅ PASS | None |
| R11 | Race conditions | ✅ PASS | Connection pool uses threading.Lock |
| R12 | safe_integration.py status() | ✅ FIXED | `safe_integration.py` created 2026-04-08. See H-SI-01. |
| R13 | Entry point importable | ✅ PASS | Manifest present; DB-only app |
| R14 | requirements.txt pinned | ✅ FIXED | `requirements.txt` created 2026-04-08 (pinned). See H-REQ-01. |
| R15 | No hardcoded dev paths | ✅ FIXED | `WILLOW_CORE` now required env var — patched 2026-04-08. See H-PATH-01. |

## Findings

### H-SI-01 — Missing safe_integration.py (P2) — FIXED 2026-04-15

**File:** `safe_integration.py`  
**Severity:** P2  
**Status:** Closed

`safe_integration.py` created. Gracefully handles Willow unreachable.

---

### H-PATH-01 — Hardcoded WILLOW_CORE Default (P2) — FIXED 2026-04-15

**File:** `squirrel_db.py`, `db/__init__.py`  
**Severity:** P2  
**Status:** Closed

`WILLOW_CORE` now required env var — raises `EnvironmentError` if unset. WSL `_resolve_host()` shim also removed; replaced with `_default_dsn()` using Unix socket peer auth.

---

### H-REQ-01 — Missing requirements.txt (P2) — FIXED 2026-04-15

**Severity:** P2  
**Status:** Closed

`requirements.txt` created with pinned `psycopg2-binary==2.9.9`.

---

## Summary

| Priority | Count | Items |
|---|---|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | H-SI-01 fixed, H-PATH-01 fixed, H-REQ-01 fixed |

---

## Level 3 Audit — Portless Compliance (2026-04-08)

b17: K2578

| # | Check | Status | Notes |
|---|---|---|---|
| R1 | No uvicorn.run / flask.run / socket listener in *.py | ✅ PASS | No HTTP server found. DB-only app. |
| R2 | HTTP port conflict (8420/8421/8422) | ✅ N/A | No HTTP server present. |
| R6 | safe-app-manifest.json has `b17` and `agent_type` fields | ✅ FIXED | Both present: b17=NNA92, agent_type=tool. Added in Level 2 rebuild. |
| R10 | Data staged to intake/ or via POST endpoints | ✅ N/A | No intake dir, no POST endpoints. DB writes only. |
| R15 | Any .py file calls sap.core.gate.authorized() | ✅ FIXED | sap/core/gate.py created 2026-04-15. All PII read/write functions in db/persons.py and db/fragments.py gated. backfill_oscar_mann.py uses bypass(). |

### Findings

**L3-R6 — Manifest missing b17 and agent_type (P2) — FIXED**
`safe-app-manifest.json` now has `"b17": "NNA92"` and `"agent_type": "tool"`. Added in Level 2 rebuild.

**L3-R15 — No sap.core.gate.authorized() call (P2) — FIXED 2026-04-15**
`sap/core/gate.py` created. `authorized()` called at the top of all PII read/write functions in `db/persons.py` and `db/fragments.py`. `backfill_oscar_mann.py` wrapped in `sap.core.gate.bypass(reason)`. Gate blocks by default; callers must set `SAP_AUTHORIZED=1` or use explicit bypass.

### L3 Summary

| Priority | Count | Items |
|---|---|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | L3-R6 fixed, L3-R15 fixed |

*ΔΣ=42*
