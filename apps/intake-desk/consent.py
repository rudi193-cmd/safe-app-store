"""The desk's binding to `subject-consent`.

The desk never asks *may this app do X?* — it asks *did the person this
account is about agree to it being kept, and to it leaving?* That is the axis
`libs/subject-consent` exists for, and this module is the thin binding over
it: scope names, and two fail-closed reads.

Absence is not consent. Every path that cannot answer "yes, verified" answers
"no".
"""
from __future__ import annotations

from pathlib import Path

from subject_consent import (  # hard dependency: no consent lib, no desk
    grant,
    permitted,
    record_disclosure,
    revoke,
)

#: May this account be kept on this device at all. Required to file.
KEEPING = "local_only"

#: May this account leave the vault as attributed testimony. Required to
#: export. Distinct from `kb_promotion`, which is de-identified structure
#: crossing into a shared KB — publication here is identified on purpose
#: ("Names Given Not Chosen"), so it needs its own grant.
PUBLICATION = "testimony_publication"


def consent_store(db_path: Path | str) -> Path:
    """The consent chain lives beside the vault it governs."""
    return Path(db_path).parent / "consent"


def may_keep(store: Path | str, narrator_id: str) -> bool:
    return permitted(store, narrator_id, KEEPING)


def may_publish(store: Path | str, narrator_id: str) -> bool:
    return permitted(store, narrator_id, PUBLICATION)


def grant_keeping(store: Path | str, narrator_id: str, granted_by: str):
    return grant(store, narrator_id, KEEPING, granted_by)


def grant_publication(store: Path | str, narrator_id: str, granted_by: str):
    return grant(store, narrator_id, PUBLICATION, granted_by)


def revoke_all(store: Path | str, narrator_id: str, revoked_by: str) -> None:
    """Withdraw both scopes. Never an erasure — a logged transition."""
    revoke(store, narrator_id, PUBLICATION, revoked_by)
    revoke(store, narrator_id, KEEPING, revoked_by)


def note_disclosure(store: Path | str, narrator_id: str, action: str, detail: str = "") -> str:
    """Append to the per-subject record a narrator (or their family) can read."""
    return record_disclosure(store, narrator_id, action, detail)
