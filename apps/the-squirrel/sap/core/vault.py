"""
sap.core.vault — Fernet-encrypted secret store for the Squirrel's box.
b17: NNA92
ΔΣ=42

Mirrors willow-mcp/vault.py (itself lifted from willow-2.0/core/vault.py);
schema is willow-data-vault/schema/01_secrets.sql verbatim. The box is
$SQUIRREL_HOME (default ~/.squirrel): vault.db + vault.key at the root,
0600 both, 0700 on the box — same layout as $WILLOW_HOME.

The crypto linchpin, per the blueprint: vault.key is generated locally,
never committed, never copied. Copy vault.db without the key and every
secret is unreadable — "agents cannot carry it out" as cryptography,
not policy.

Secrets NEVER go through the journal. Squirrel.md is append-only history —
a secret typed there is a secret kept in plaintext forever. Set secrets
from a terminal instead, where the value is prompted and never echoed:

    python3 -m sap.core.vault set willowgate_key_fpr
    python3 -m sap.core.vault list | get NAME | delete NAME | provision

Known consumers:
    willowgate_key_fpr — operator PGP fingerprint; when present, the
    willow-gate check-in/out ledger is encrypted to it (sap/core/gate.py
    reads env WILLOWGATE_KEY_FPR first, then this vault).
"""

import os
import sqlite3
import sys
from pathlib import Path


def squirrel_home() -> Path:
    return Path(os.environ.get("SQUIRREL_HOME", Path.home() / ".squirrel"))


class VaultUnavailable(RuntimeError):
    """cryptography is not installed — the vault cannot open."""


def _fernet_cls():
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise VaultUnavailable(
            "vault needs the 'cryptography' package (see requirements.txt)"
        ) from e
    return Fernet


class Vault:
    def __init__(self, vault_path=None, key_path=None):
        home = squirrel_home()
        self._vault = Path(vault_path) if vault_path is not None else home / "vault.db"
        self._key_path = Path(key_path) if key_path is not None else home / "vault.key"
        self._fernet = None

    def init(self):
        """Create vault DB and Fernet key if they don't exist."""
        Fernet = _fernet_cls()
        self._vault.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._key_path.exists():
            fd = os.open(str(self._key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())

        self._key_path.chmod(0o600)
        self._fernet = Fernet(self._key_path.read_bytes())

        conn = sqlite3.connect(str(self._vault))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                name TEXT PRIMARY KEY,
                value BLOB NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        self._vault.chmod(0o600)

    def _get_fernet(self):
        if self._fernet is None:
            self._fernet = _fernet_cls()(self._key_path.read_bytes())
        return self._fernet

    def write(self, name: str, value: str) -> None:
        encrypted = self._get_fernet().encrypt(value.encode())
        conn = sqlite3.connect(str(self._vault))
        conn.execute(
            "INSERT INTO secrets (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, encrypted))
        conn.commit()
        conn.close()

    def read(self, name: str):
        conn = sqlite3.connect(str(self._vault))
        row = conn.execute(
            "SELECT value FROM secrets WHERE name = ?", (name,)).fetchone()
        conn.close()
        if not row:
            return None
        return self._get_fernet().decrypt(row[0]).decode()

    def has(self, name: str) -> bool:
        return self.read(name) is not None

    def list_keys(self):
        conn = sqlite3.connect(str(self._vault))
        rows = conn.execute("SELECT name FROM secrets ORDER BY name").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def delete(self, name: str) -> bool:
        # Extension over willow-mcp's Vault (which has no delete yet).
        conn = sqlite3.connect(str(self._vault))
        cur = conn.execute("DELETE FROM secrets WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0


def default_vault() -> Vault:
    """Vault at $SQUIRREL_HOME, initializing if needed. Same guard as
    willow-mcp: a db without its key is a hard stop, not a re-init."""
    v = Vault()
    home = squirrel_home()
    db_exists = (home / "vault.db").exists()
    key_exists = (home / "vault.key").exists()
    if db_exists and not key_exists:
        raise FileNotFoundError(
            f"Vault database exists but key file is missing: {v._key_path}\n"
            "Restore the key from backup or delete the vault and re-initialize.")
    if not db_exists:
        v.init()
    return v


def read_secret(name: str):
    """Best-effort read for consumers with a fallback path (e.g. the gate
    checking for an operator PGP fingerprint): missing vault, missing
    cryptography, or missing secret all resolve to None. A present-but-
    unopenable vault (db without key) still raises — that is damage,
    not absence."""
    home = squirrel_home()
    if not (home / "vault.db").exists():
        return None
    try:
        return default_vault().read(name)
    except VaultUnavailable:
        return None


def provision(box=None) -> Path:
    """Stand up the Squirrel's box (idempotent) — the local mirror of
    willow-data-vault/bootstrap/provision.sh: layout + perms + vault.
    Vault init is best-effort and NON-FATAL, per the blueprint: without
    cryptography the box still stands and Vault.init() finishes the job
    on a later run."""
    box = Path(box) if box else squirrel_home()
    box.mkdir(parents=True, exist_ok=True)
    box.chmod(0o700)
    (box / "willowgate").mkdir(exist_ok=True)  # gate registry + ledger + announcements
    try:
        Vault(box / "vault.db", box / "vault.key").init()
    except VaultUnavailable as e:
        print(f"vault: {e} — box stands, vault deferred", file=sys.stderr)
    for name in ("vault.db", "vault.key", "receipts.db"):
        p = box / name
        if p.exists():
            p.chmod(0o600)
    return box


def _cli(argv):
    """Terminal-only surface. Secrets are prompted, never taken as argv —
    argv lands in shell history."""
    import getpass
    cmd = argv[0] if argv else "help"
    if cmd == "provision":
        print(f"box: {provision()}")
    elif cmd == "list":
        for name in default_vault().list_keys():
            print(name)
    elif cmd == "set" and len(argv) == 2:
        value = getpass.getpass(f"value for {argv[1]!r} (not echoed): ")
        if not value:
            print("empty value — nothing stored", file=sys.stderr)
            return 1
        default_vault().write(argv[1], value)
        print(f"stored {argv[1]!r}")
    elif cmd == "get" and len(argv) == 2:
        value = default_vault().read(argv[1])
        if value is None:
            print(f"no secret named {argv[1]!r}", file=sys.stderr)
            return 1
        print(value)
    elif cmd == "delete" and len(argv) == 2:
        gone = default_vault().delete(argv[1])
        print(f"deleted {argv[1]!r}" if gone else f"no secret named {argv[1]!r}")
    else:
        print("usage: python3 -m sap.core.vault "
              "provision | list | set NAME | get NAME | delete NAME", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
