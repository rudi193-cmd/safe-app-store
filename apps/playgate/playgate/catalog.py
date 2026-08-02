"""The kid-facing catalog: a curated list, read from disk, never fetched.

There is no third-party store behind this. The catalog is a file an operator
edits, which is the whole point — the failure this app exists to answer is a
child sent to the open web to find a game, where the ranking is bought and the
play button is the bait.

Every entry carries an interruption record. Entries that do not are rejected at
load, not skipped: an app in a child's catalog with nothing recorded about how
often it stops them is exactly the silence this app refuses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .interruption import Interruption, InterruptionError, weakest

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "data" / "catalog.json"

REQUIRED_FIELDS = ("id", "title", "blurb", "age_band", "abi", "package")


@dataclass(frozen=True)
class App:
    id: str
    title: str
    blurb: str
    age_band: str
    abi: str
    package: str
    version: str | None
    sha256: str | None
    apk_path: str | None
    interruption: Interruption
    tracker_provenance: str

    def view(self, installed_version: str | None = None) -> dict:
        """What the kid and parent UIs are given.

        Four unweighted facts about interruption and no composite of them. A
        single number would be built from weights somebody picked, displayed,
        sorted on, and within two releases optimised against — at which point it
        would measure compliance with the scoring function instead of
        interruption, in the same way time-on-app stopped measuring enjoyment.

        `confidence` is not a score either. It is the weakest input, named.
        """
        effective = self.interruption.effective(installed_version or self.version)
        return {
            "id": self.id,
            "title": self.title,
            "blurb": self.blurb,
            "age_band": self.age_band,
            "abi": self.abi,
            "package": self.package,
            "version": self.version,
            "interruption": effective.to_json(),
            "confidence": weakest(effective.provenance, self.tracker_provenance),
        }


def _parse(entry: dict, source: Path) -> App:
    missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
    if missing:
        raise InterruptionError(f"{source}: entry {entry.get('id', '?')} missing {missing}")
    try:
        interruption = Interruption.from_json(entry.get("interruption"))
    except InterruptionError as exc:
        raise InterruptionError(f"{source}: {entry['id']}: {exc}") from exc

    tracker = entry.get("tracker_provenance", "assumed")
    return App(
        id=entry["id"],
        title=entry["title"],
        blurb=entry["blurb"],
        age_band=entry["age_band"],
        abi=entry["abi"],
        package=entry["package"],
        version=entry.get("version"),
        sha256=entry.get("sha256"),
        apk_path=entry.get("apk_path"),
        interruption=interruption,
        tracker_provenance=tracker,
    )


def load(path: Path | None = None) -> "list[App]":
    source = path or DEFAULT_CATALOG
    raw = json.loads(source.read_text())
    entries = raw.get("apps", [])
    apps = [_parse(entry, source) for entry in entries]

    seen: set[str] = set()
    for app in apps:
        if app.id in seen:
            raise InterruptionError(f"{source}: duplicate app id {app.id!r}")
        seen.add(app.id)
    return apps


def search(apps: "list[App]", query: str | None) -> "list[App]":
    """Substring match over title, blurb and age band.

    No ranking. There is no engagement signal to rank by and nothing here is
    competing for a slot, so the order is the order the operator wrote.
    """
    if not query:
        return list(apps)
    needle = query.strip().lower()
    if not needle:
        return list(apps)
    return [
        app for app in apps
        if needle in app.title.lower()
        or needle in app.blurb.lower()
        or needle in app.age_band.lower()
    ]


def by_id(apps: "list[App]", app_id: str) -> "App | None":
    for app in apps:
        if app.id == app_id:
            return app
    return None
