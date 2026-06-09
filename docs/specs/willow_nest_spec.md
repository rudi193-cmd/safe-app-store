# Willow Nest — App Spec
**Date:** 2026-04-27 | **Status:** Approved | **b17:** B2DA2
**Reviewed by:** hanuman (2026-04-27) — 3 gaps addressed: photo track expansion, test coverage section, compost config location
**Repo:** `~/github/willow-nest`

## What It Is

File intake pipeline: classifies files from drop zones by track (journal, legal, handoffs, knowledge, narrative, specs, photos), routes each to a canonical destination, then runs track-specific pipeline stages (compost, scrub, promote, archive). Entry point: `python3 nest.py`.

---

## What It Actually Does

**Not** a UI shell over MCP tools. **Not** a frictionless note-drop zone. A filesystem pipeline that processes USER's documents from Windows migration drop zones into the correct locations on the Linux system.

Drop zones:
- `~/Desktop/Nest/`
- `~/Ashokoa/Nest/processed/`

Pipeline stages per track:
| Track | Stages |
|---|---|
| journal | compost → promote |
| legal | scrub |
| knowledge | promote |
| narrative | compost → promote |
| handoffs | compost → promote |
| specs | compost → promote |
| photos_personal | (none — sorted to personal/photos/personal/) |
| photos_camera | (none — sorted to personal/photos/camera/) |
| screenshots | (none — sorted to personal/photos/screenshots/) |
| unknown | quarantine |

---

## Architecture

```
nest.py (consent layer + orchestrator)
  ├── classify.py     — pure function: filename → track (no I/O)
  ├── router.py       — proposes destination, moves file, writes store record
  ├── store_bridge.py — WillowStore wrapper (files/store collection)
  └── pipeline/
        ├── compost.py   — LLM summarization (Groq/Cerebras/Anthropic fleet)
        ├── scrub.py     — PII/sensitive content handling
        ├── promote.py   — writes LOAM knowledge atom for promoted files
        └── archive.py   — moves to cold storage
```

**Store:** WillowStore (SOIL) at `~/.willow/store`, collection `files/store`. Each file gets a b17 record tracking nest_status through the pipeline.

**Classification:** Pure regex/keyword matching on filename. Priority: journal > legal > handoffs > knowledge > specs > narrative > photos. No LLM at classify time.

**LLM:** Only at compost stage (cloud fleet: Groq, Cerebras, Anthropic). `local_processing: 0.85`.

---

## SAP Manifest (actual, from repo)

```json
{
  "app_id": "willow-nest",
  "b17": "B2DA2",
  "permissions": ["file_read", "file_write", "cloud_llm_free", "knowledge_store_write"],
  "privacy_tier": "client_only",
  "local_processing": 0.85,
  "entry_point": "nest:main"
}
```

---

## catalog.json Entry (safe-app-store)

```json
{
  "id": "willow-nest",
  "name": "Willow Nest",
  "description": "File intake pipeline. Classifies, routes, and processes documents from drop zones into canonical storage. Compost, scrub, promote, archive.",
  "status": "beta",
  "path": "../willow-nest",
  "tags": ["pipeline", "files", "intake", "local"]
}
```

Note: `path` is a sibling repo, not inside `safe-app-store/apps/`.

---

## 1B Model Interaction

Limited. Classification (`classify.py`) is pure Python with no LLM — a 1B model could call it. But the compost stage uses a cloud LLM fleet, and the full pipeline orchestration in `nest.py` requires filesystem access and store writes. The pipeline is not 1B-safe at execution time. A 1B model could read a `files/store` record (one atom, one status field) but not run a pipeline stage.

---

## What Was Wrong in the Previous Spec

The first version of this spec described willow-nest as "a thin UI shell over willow_nest_scan/queue/file MCP tools" with "no schema ownership." Both claims were invented without reading the actual repo. The real app:
- Does not use the MCP nest tools at all
- Owns a WillowStore collection (files/store)
- Is a full pipeline, not a UI shell
- Has b17 B2DA2, not NSTP1

**Root cause:** Only checked `safe-app-store/apps/willow-nest/` (empty), never checked sibling repos.

---

## Test Coverage

One test file exists: `tests/test_classify.py` (covers the pure classifier).

**Untested:** `router.py`, `store_bridge.py`, `pipeline/compost.py`, `pipeline/scrub.py`, `pipeline/promote.py`, `pipeline/archive.py`. All four pipeline stages and the file router have no tests. Before running this pipeline on real migration files, the untested stages are a real risk — especially scrub (PII handling) and promote (writes LOAM atoms).

---

## Open Items

- [ ] Add willow-nest catalog entry to `safe-app-store/catalog.json`
- [ ] Verify `router.py` destination paths are correct for Linux layout
- [ ] Confirm compost LLM fleet config: `~/github/willow-1.9/credentials.json` — must have Groq, Cerebras, or Anthropic keys present
- [ ] Write tests for router.py, store_bridge.py, and pipeline stages before running on real files

ΔΣ=42
