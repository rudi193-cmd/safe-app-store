"""
sap.core.consent — the box's standing switches.
b17: NNA92
ΔΣ=42

Squirrel-scale mirror of willow-mcp's consent.* rows: a settings file in
the box, read before anything renders a path off the machine.

    $SQUIRREL_HOME/settings.json
    { "consent": { "online": true } }

`online` governs whether the Squirrel renders links to outside archives
(search cards, the sources browser). After the Wikipedia demotion the app
makes ZERO network calls of its own — every outbound motion is a link the
user clicks, so the click is the per-use confirm authority and this switch
is the standing one. If a live lookup ever returns, it gets its own
consent line, default off — a link and a socket are different animals.

Read posture, in lease.py's spirit but with the poles named:
  - ABSENT file    -> factory defaults (online=True: links are the
                      request-without-confirm half; the app is dead
                      without its sources). Absence is a fresh box.
  - DAMAGED file   -> everything off. A settings file that exists but
                      cannot be read is not a preference, it's a wound —
                      fail closed and say so.

One deliberate divergence from willow-mcp, where consent is read-only to
the server ("a consumer that writes the policy it is checked against is
not a gate"): here set_online() exists and the Privacy page calls it.
This is a single-operator box and the web UI on 127.0.0.1 IS the
operator's console — the human clicking the switch is the same authority
who would edit the file. Every flip is receipted.
"""

import json
import os

from sap.core.vault import squirrel_home

DEFAULTS = {"consent": {"online": True}}


def settings_path():
    return squirrel_home() / "settings.json"


def _read():
    """Parsed settings dict, DEFAULTS if absent, None if damaged."""
    p = settings_path()
    if not p.exists():
        return json.loads(json.dumps(DEFAULTS))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def damaged() -> bool:
    return _read() is None


def online() -> bool:
    data = _read()
    if data is None:
        return False  # a wound, not a preference — fail closed
    section = data.get("consent")
    if not isinstance(section, dict):
        return False
    return section.get("online", DEFAULTS["consent"]["online"]) is True


def set_online(value: bool) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _read() or {}  # writing a fresh file over a damaged one is the repair
    section = data.get("consent") if isinstance(data.get("consent"), dict) else {}
    section["online"] = bool(value)
    data["consent"] = section
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
