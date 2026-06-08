#!/usr/bin/env python3
"""
provision_user_identity.py — Generate ~/.willow/user_identity.json

Run once per machine. Idempotent — skips if file already exists.
willow-seed calls this during install; users can also run it standalone.

Usage:
    python3 scripts/provision_user_identity.py
    python3 scripts/provision_user_identity.py --force   # overwrite existing
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

IDENTITY_PATH = Path.home() / ".willow" / "user_identity.json"


def provision(force: bool = False) -> bool:
    if IDENTITY_PATH.exists() and not force:
        data = json.loads(IDENTITY_PATH.read_text())
        print(f"[provision] user_identity.json already exists — uuid: {data.get('uuid')}")
        return True

    IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    identity = {
        "uuid": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Sovereign user identity. All apps write to user-{uuid}/<app>/ namespace.",
    }
    IDENTITY_PATH.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"[provision] created user_identity.json — uuid: {identity['uuid']}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Provision ~/.willow/user_identity.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing file")
    args = parser.parse_args()
    success = provision(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
