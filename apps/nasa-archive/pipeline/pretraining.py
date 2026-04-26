"""
NASA Archive -- SAFE OS Pre-Training Pipeline
============================================
Processes PUBLIC RECORD sources only.

PRIVACY HARD RULE:
  This pipeline writes source_type='public_record' ONLY.
  Private content (oral history sessions, private comms) = HARD STOP.
  Oral history agent handles oral_history_consented separately.

Public sources:
  1. scoot.net rally data (data/rallies/{slug}/meta.json)
  2. Vespa Motorsport Podcast (MP3 -> Whisper -> entity extraction)
  3. Club/rally web archives (Modern Vespa, club sites, obituaries)

Usage:
  python pipeline/pretraining.py --source scootnet
  python pipeline/pretraining.py --source podcast --path /path/to/ep4.mp3
  python pipeline/pretraining.py --source web --url https://modernvespa.com/...
  python pipeline/pretraining.py --source willow [--willow-username Sweet-Pea-Rudi19]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# Willow fleet API -- calls Willow server instead of importing core directly
import requests as _fleet_requests

WILLOW_FLEET_URL = "http://localhost:8420/api/fleet/ask"


def _fleet_ask(prompt: str, tier: str = "free"):
    """Call Willow's fleet endpoint."""
    try:
        r = _fleet_requests.post(
            WILLOW_FLEET_URL,
            json={"prompt": prompt, "tier": tier, "source": "nasa-archive"},
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()

            class _R:
                content  = data.get("response", "")
                provider = data.get("provider", "unknown")

            return _R()
    except Exception:
        pass
    return None


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("pretraining")

# ---- NASA Hook Triggers ----------------------------------------------------
# Applied to text chunks. If any trigger matches, extract entities from that chunk.

HOOKS: dict[str, list[str]] = {
    "importance":   ["very well known", "legendary", "iconic", "founder of", "started the"],
    "person":       ["wade parker", "matthew noli", "colin shattuck", "phil lombardo",
                     "missi kroge", "chris hyder", "chopper john", "gabe"],
    "shop":         ["scooters", "motorsport", "cycles", "garage", "shop"],
    "rally":        ["tng", "mile high mayhem", "king tutt putt", "amerivespa",
                     "rally", "run", "scootfest", "scootarama"],
    "media":        ["scoot! magazine", "vespa motorsport podcast", "podcast episode"],
    "venue":        ["tower bar", "calabasas campsite", "the crypt", "congress bar",
                     "abbey tavern", "pub scouts"],
    "incident":     ["died", "shooting", "accident", "passed away", "in memoriam"],
    "manufacturer": ["vespa", "lambretta", "honda", "stella", "bajaj"],
    "geo":          ["san diego scene", "denver scene", "tucson scene", "phoenix scene",
                     "chicago scene", "new england scene", "atlanta scene"],
    "club":         ["pharaohs", "secret servix", "ace", "bottle rockets", "jedi knights",
                     "sqream", "pub scouts", "blue smoke", "jett sett", "hard pack"],
}

EXTRACT_PROMPT = """\
You are an archivist for the North America Scooter Archive (NASA).
Extract structured entities from the following text.

Return ONLY a JSON array. Each item must follow this schema:
{{
  "entity_type": "rally" | "club" | "person" | "shop" | "venue" | "event",
  "name": "<canonical name>",
  "year": <integer or null>,
  "city": "<city or null>",
  "state": "<state abbreviation or null>",
  "description": "<1-2 sentence summary or null>",
  "confidence": "high" | "medium" | "low"
}}

Rules:
- Only extract entities explicitly named in the text.
- Do not invent names, dates, or locations.
- If a detail is not stated, use null.
- "high" confidence = name + at least one corroborating fact stated.
- "medium" = name present, supporting details vague.
- "low" = inferred from context.

Text:
{text}

Hook that triggered extraction: {hook}

JSON array:"""


class PreTrainingPipeline:
    """
    Processes public-record sources and writes to the oral_* tables in Postgres
    (schema nasa_archive). source_type is always 'public_record' -- no exceptions.
    """

    DATA_DIR = Path(__file__).parent.parent / "data" / "rallies"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        if not dry_run:
            # Import lazily so dry_run works without WILLOW_DB_URL set
            import sys as _sys
            _repo = Path(__file__).parent.parent
            if str(_repo) not in _sys.path:
                _sys.path.insert(0, str(_repo))
            from archive_db.db import get_connection, init_schema
            self._get_connection = get_connection
            init_schema()

    # ---- Internal DB helpers ------------------------------------------------

    def _conn(self):
        """Return a fresh Postgres connection (caller must close/use as context)."""
        return self._get_connection()

    def _upsert(self, table: str, record: dict, conflict_col: str = "name") -> None:
        """
        Idempotent insert. Existing rows matching conflict_col are ignored (DO NOTHING).
        For known tables the conflict target in core/db._PG_CONFLICT_TARGETS handles updates.
        """
        if self.dry_run:
            return
        # Remove None values -- Postgres rejects null for non-nullable cols
        clean = {k: v for k, v in record.items() if v is not None}
        if not clean:
            return
        cols   = list(clean.keys())
        vals   = list(clean.values())
        ph     = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({ph}) "
            f"ON CONFLICT ({conflict_col}) DO NOTHING"
        )
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, vals)
                conn.commit()
        except Exception as e:
            log.warning("Upsert failed %s %s: %s", table, clean.get("name", "?"), e)

    def _select_one(self, table: str, col: str, val) -> dict | None:
        """Return first row where col = val, or None."""
        try:
            with self._conn() as conn:
                import sqlite3 as _sqlite3
                conn.row_factory = _sqlite3.Row
                cur = conn.cursor()
                cur.execute(f"SELECT * FROM {table} WHERE {col} = %s LIMIT 1", (val,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.warning("Select failed %s.%s=%s: %s", table, col, val, e)
            return None

    def _insert_one(self, table: str, record: dict) -> str | None:
        """Insert a row and return the generated UUID id, or None on failure."""
        clean = {k: v for k, v in record.items() if v is not None}
        if not clean:
            return None
        cols     = list(clean.keys())
        vals     = list(clean.values())
        ph       = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)
        sql      = f"INSERT INTO {table} ({col_list}) VALUES ({ph}) RETURNING id"
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(sql, vals)
                row = cur.fetchone()
                conn.commit()
                return str(row[0]) if row else None
        except Exception as e:
            log.warning("Insert failed %s: %s", table, e)
            return None

    # ---- Source: scoot.net rally metadata -----------------------------------

    def process_rally_data(self) -> int:
        """
        Walk data/rallies/{slug}/meta.json and upsert each rally into oral_events.
        Returns number of records upserted.
        """
        count = 0
        for meta_path in sorted(self.DATA_DIR.glob("*/meta.json")):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)

            dir_slug    = meta_path.parent.name
            meta_slug   = meta.get("slug") or dir_slug
            title       = meta.get("title") or dir_slug
            year        = meta.get("year")
            photo_count = meta.get("photo_count", 0)

            record = {
                "name":         title,
                "event_year":   year,
                "archive_slug": dir_slug,
                "source_type":  "public_record",
                "confidence":   "high",
                "sources":      json.dumps([{
                    "type":       "web_archive",
                    "url":        meta.get("url") or f"http://scoot.net/gallery/{meta_slug}/",
                    "timestamp":  None,
                    "confidence": "high",
                }]),
            }

            if self.dry_run:
                if count < 5 or count % 200 == 0:
                    log.info("[DRY RUN] oral_events: %s (%s) photos=%s", title, year, photo_count)
            else:
                self._upsert("oral_events", record, conflict_col="archive_slug")
            count += 1
            if count % 100 == 0:
                log.info("Processed %d rallies...", count)

        action = "would upsert" if self.dry_run else "upserted"
        log.info("Rally data: %d records %s", count, action)
        return count

    # ---- Source: Podcast audio ----------------------------------------------

    def process_podcast(self, mp3_path: str | Path, episode_url: str = "") -> list[dict]:
        """
        Transcribe a podcast MP3 with Whisper, then extract entities.
        Requires: pip install openai-whisper
        """
        try:
            import whisper  # type: ignore
        except ImportError:
            log.error("openai-whisper not installed. Run: pip install openai-whisper")
            return []

        log.info("Transcribing %s ...", mp3_path)
        model = whisper.load_model("base")
        result = model.transcribe(str(mp3_path))
        text: str = result["text"]

        source = {
            "type":       "podcast",
            "url":        episode_url or str(mp3_path),
            "timestamp":  None,
            "confidence": "high",
        }
        entities = self.extract_entities_from_text(text, source)
        self._write_entities(entities)
        return entities

    # ---- Source: Web archive ------------------------------------------------

    def process_web_page(self, url: str) -> list[dict]:
        """
        Scrape a public page (Modern Vespa, club site, obituary) and extract entities.
        """
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "NASAArchive/1.0"})
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error("Fetch failed %s: %s", url, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "footer", "script", "style"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)

        source = {"type": "web_archive", "url": url, "timestamp": None, "confidence": "medium"}
        entities = self.extract_entities_from_text(text, source)
        self._write_entities(entities)
        return entities

    # ---- Source: Willow knowledge graph -------------------------------------

    def process_willow_knowledge(
        self,
        username: str = "Sweet-Pea-Rudi19",
        sean_entity_id: int = 2,
    ) -> dict:
        """
        Import scootering narrative atoms from Willow's knowledge table
        (schema sweet_pea_rudi19, table knowledge / knowledge_entities).

        Confidence weighting by graph distance from Sean Campbell entity[2]:
          Direct Sean connection -> oral_history_consented, high
          1-hop (atoms sharing an entity with Sean's atoms) -> public_record, medium
          No Sean connection -> public_record, low

        Returns dict with inserted counts per table.
        """
        from archive_db.db import get_willow_knowledge_connection

        log.info("Connecting to Willow knowledge (PG schema sweet_pea_rudi19)...")
        wconn = get_willow_knowledge_connection()

        try:
            import sqlite3 as _sqlite3
            wconn.row_factory = _sqlite3.Row
            wcur = wconn.cursor()

            # -- Build graph-distance sets ------------------------------------

            wcur.execute(
                "SELECT knowledge_id FROM knowledge_entities WHERE entity_id = %s",
                (sean_entity_id,),
            )
            sean_atom_ids: set[int] = {r[0] for r in wcur.fetchall()}

            wcur.execute(
                """
                SELECT DISTINCT ke2.entity_id
                FROM knowledge_entities ke1
                JOIN knowledge_entities ke2 ON ke1.knowledge_id = ke2.knowledge_id
                WHERE ke1.entity_id = %s AND ke2.entity_id != %s
                """,
                (sean_entity_id, sean_entity_id),
            )
            sean_adjacent: set[int] = {r[0] for r in wcur.fetchall()}

            hop1_ids: set[int] = set()
            if sean_adjacent:
                placeholders = ", ".join(["%s"] * len(sean_adjacent))
                wcur.execute(
                    f"SELECT DISTINCT knowledge_id FROM knowledge_entities "
                    f"WHERE entity_id IN ({placeholders})",
                    list(sean_adjacent),
                )
                hop1_ids = {r[0] for r in wcur.fetchall()} - sean_atom_ids

            # -- Query scootering atoms ---------------------------------------

            SCOOTER_TERMS = ["pharaoh", "scoot", "rally", "vespa", "lambretta", "camp scoot", "patch"]
            SCOOTER_CATS  = ("narrative", "personal", "personal_document", "archive", "media")
            cat_ph    = ", ".join(["%s"] * len(SCOOTER_CATS))
            kw_conds  = " OR ".join(
                "(LOWER(title) LIKE %s OR LOWER(summary) LIKE %s OR LOWER(content_snippet) LIKE %s)"
                for _ in SCOOTER_TERMS
            )
            params: list = list(SCOOTER_CATS)
            for t in SCOOTER_TERMS:
                params += [f"%{t}%", f"%{t}%", f"%{t}%"]

            wcur.execute(
                f"SELECT id, title, summary, content_snippet, category, created_at "
                f"FROM knowledge "
                f"WHERE category IN ({cat_ph}) AND ({kw_conds}) "
                f"ORDER BY id",
                params,
            )
            scoot_rows = wcur.fetchall()

        finally:
            wconn.close()

        # Deduplicate
        seen: set[int] = set()
        atoms = []
        for row in scoot_rows:
            rid = row["id"] if hasattr(row, "__getitem__") else row[0]
            if rid not in seen:
                seen.add(rid)
                atoms.append(row)

        sean_in_batch = sum(1 for a in atoms if a["id"] in sean_atom_ids)
        log.info(
            "Willow import: %d scootering atoms (%d Sean-direct, %d 1-hop, %d other)",
            len(atoms), sean_in_batch,
            sum(1 for a in atoms if a["id"] in hop1_ids),
            sum(1 for a in atoms if a["id"] not in sean_atom_ids and a["id"] not in hop1_ids),
        )

        # -- Upsert Sean's oral_persons record (narrator anchor) --------------

        sean_narrator_id: str | None = None
        if not self.dry_run:
            existing = self._select_one("oral_persons", "club_name", "Sweet-Pea-Rudi19")
            if existing:
                sean_narrator_id = str(existing["id"])
            else:
                sean_narrator_id = self._insert_one("oral_persons", {
                    "club_name":   "Sweet-Pea-Rudi19",
                    "home_city":   "Albuquerque",
                    "home_state":  "NM",
                    "bio":         "Pharaohs Scooter Club member since 2005. Camp Scoot rally organizer since 2003.",
                    "source_type": "oral_history_consented",
                    "confidence":  "high",
                    "sources":     json.dumps([{
                        "type":       "willow_knowledge",
                        "url":        f"willow://entities/{sean_entity_id}",
                        "timestamp":  None,
                        "confidence": "high",
                    }]),
                })

        # -- Import atoms -----------------------------------------------------

        counts = {"oral_stories": 0, "oral_persons": 0, "oral_clubs": 0, "oral_events": 0}

        for atom in atoms:
            atom_id  = atom["id"]
            title    = atom["title"] or ""
            summary  = atom["summary"] or ""
            snippet  = atom["content_snippet"] or ""

            if atom_id in sean_atom_ids:
                source_type = "oral_history_consented"
                confidence  = "high"
            elif atom_id in hop1_ids:
                source_type = "public_record"
                confidence  = "medium"
            else:
                source_type = "public_record"
                confidence  = "low"

            text            = "\n\n".join(p for p in [title, summary, snippet] if p).strip()
            capture_session = f"willow-k{atom_id}"
            source_entry    = {
                "type":       "willow_knowledge",
                "url":        f"willow://knowledge/{atom_id}",
                "timestamp":  atom["created_at"],
                "confidence": confidence,
            }

            if self.dry_run:
                if counts["oral_stories"] < 5 or counts["oral_stories"] % 10 == 0:
                    log.info("[DRY RUN] oral_stories: '%s' (%s, %s)", title[:60], confidence, source_type)
                counts["oral_stories"] += 1
            else:
                existing = self._select_one("oral_stories", "capture_session", capture_session)
                if not existing:
                    record: dict = {
                        "title":           title[:255] or None,
                        "content":         text[:10000],
                        "source":          "written",
                        "capture_session": capture_session,
                        "source_type":     source_type,
                        "confidence":      confidence,
                        "sources":         json.dumps([source_entry]),
                        "summary":         summary[:1000] or None,
                    }
                    if sean_narrator_id and atom_id in sean_atom_ids:
                        record["narrator_id"] = sean_narrator_id

                    new_id = self._insert_one("oral_stories", record)
                    if new_id:
                        counts["oral_stories"] += 1

            if not self.dry_run:
                entities = self.extract_entities_from_text(text, source_entry)
                self._write_entities(entities)
                counts["oral_persons"] += sum(1 for e in entities if e.get("entity_type") == "person")
                counts["oral_clubs"]   += sum(1 for e in entities if e.get("entity_type") == "club")
                counts["oral_events"]  += sum(1 for e in entities if e.get("entity_type") == "rally")

        action = "would process" if self.dry_run else "processed"
        log.info("Willow import complete: %d atoms %s: %s", len(atoms), action, counts)
        return counts

    # ---- Entity extraction via hooks + fleet --------------------------------

    def extract_entities_from_text(
        self, text: str, source: dict, chunk_size: int = 1500
    ) -> list[dict]:
        """
        Apply all 10 NASA hooks to text chunks.
        For each matching chunk, call the free fleet to extract structured entities.
        Returns list of entity dicts ready for Postgres.
        """
        entities: list[dict] = []
        words = text.split()
        step  = chunk_size - 100  # 100-word overlap
        for i in range(0, len(words), step):
            chunk       = " ".join(words[i : i + chunk_size])
            chunk_lower = chunk.lower()

            triggered_hooks = [
                hook for hook, triggers in HOOKS.items()
                if any(t in chunk_lower for t in triggers)
            ]
            if not triggered_hooks:
                continue

            hook_label = ", ".join(triggered_hooks)
            safe_chunk = chunk.replace("{", "{{").replace("}", "}}")
            prompt     = EXTRACT_PROMPT.format(text=safe_chunk, hook=hook_label)

            raw = self._call_fleet(prompt)
            if not raw:
                continue

            parsed = self._parse_json_array(raw)
            for item in parsed:
                item["sources"]     = [source]
                item["source_type"] = "public_record"
            entities.extend(parsed)

        # Deduplicate by (entity_type, name)
        seen: set[tuple] = set()
        unique: list[dict] = []
        for e in entities:
            key = (e.get("entity_type", ""), e.get("name", "").lower())
            if key not in seen:
                seen.add(key)
                unique.append(e)

        return unique

    # ---- Write to Postgres --------------------------------------------------

    def _write_entities(self, entities: list[dict]) -> None:
        """Route each extracted entity to the correct oral_* table."""
        for entity in entities:
            etype = entity.get("entity_type", "")
            if etype == "rally":
                self._upsert("oral_events", {
                    "name":        entity.get("name"),
                    "event_year":  entity.get("year"),
                    "description": entity.get("description"),
                    "source_type": "public_record",
                    "confidence":  entity.get("confidence", "medium"),
                    "sources":     json.dumps(entity.get("sources", [])),
                }, conflict_col="name")
            elif etype == "club":
                self._upsert("oral_clubs", {
                    "name":        entity.get("name"),
                    "city":        entity.get("city"),
                    "state":       entity.get("state"),
                    "notes":       entity.get("description"),
                    "source_type": "public_record",
                    "confidence":  entity.get("confidence", "medium"),
                    "sources":     json.dumps(entity.get("sources", [])),
                }, conflict_col="name")
            elif etype == "person":
                self._upsert("oral_persons", {
                    "club_name":   entity.get("name"),
                    "home_city":   entity.get("city"),
                    "home_state":  entity.get("state"),
                    "bio":         entity.get("description"),
                    "source_type": "public_record",
                    "confidence":  entity.get("confidence", "medium"),
                    "sources":     json.dumps(entity.get("sources", [])),
                }, conflict_col="club_name")
            elif etype in ("shop", "venue"):
                self._upsert("oral_locations", {
                    "name":          entity.get("name"),
                    "city":          entity.get("city"),
                    "state":         entity.get("state"),
                    "location_type": etype,
                    "notes":         entity.get("description"),
                    "source_type":   "public_record",
                    "confidence":    entity.get("confidence", "medium"),
                    "sources":       json.dumps(entity.get("sources", [])),
                }, conflict_col="name")
            else:
                log.debug("Skipping entity_type=%s name=%s", etype, entity.get("name"))

    # ---- Fleet helpers ------------------------------------------------------

    def _call_fleet(self, prompt: str, retries: int = 3) -> str | None:
        """Call the Willow free fleet with exponential backoff."""
        for attempt in range(retries):
            try:
                resp = _fleet_ask(prompt, tier="free")
                if resp:
                    return resp.content
            except Exception as e:
                log.warning("Fleet attempt %d failed: %s", attempt + 1, e)
            time.sleep(2 ** attempt)
        return None

    @staticmethod
    def _parse_json_array(text: str) -> list[dict]:
        """Extract the first JSON array from LLM output. Returns [] on parse failure."""
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        try:
            data = json.loads(text[start:end])
            return [item for item in data if isinstance(item, dict) and item.get("name")]
        except json.JSONDecodeError:
            log.debug("JSON parse failed: %s", text[:200])
            return []


# ---- CLI -------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NASA Archive pre-training pipeline")
    parser.add_argument("--source",   choices=["scootnet", "podcast", "web", "willow"], required=True)
    parser.add_argument("--path",     help="Path to MP3 file (podcast mode)")
    parser.add_argument("--url",      help="URL to scrape (web mode)")
    parser.add_argument("--username", default="Sweet-Pea-Rudi19",
                        help="Willow username for knowledge schema (willow mode)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Preview without writing to Postgres")
    args = parser.parse_args()

    # Load .env from repo root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    p = PreTrainingPipeline(dry_run=args.dry_run)

    if args.source == "scootnet":
        n = p.process_rally_data()
        action = "would upsert" if args.dry_run else "upserted"
        print(f"Done: {n} rally records {action}")

    elif args.source == "podcast":
        if not args.path:
            parser.error("--path required for podcast mode")
        entities = p.process_podcast(args.path)
        print(f"Done: {len(entities)} entities extracted")

    elif args.source == "web":
        if not args.url:
            parser.error("--url required for web mode")
        entities = p.process_web_page(args.url)
        print(f"Done: {len(entities)} entities extracted")

    elif args.source == "willow":
        counts = p.process_willow_knowledge(username=args.username)
        action = "would import" if args.dry_run else "imported"
        print(f"Done: {action}: {counts}")
