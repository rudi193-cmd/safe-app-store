import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class Command:
    name: str
    args: list
    raw: str

_TRIGGER = re.compile(r'@squirrel:\s+(.+)', re.IGNORECASE)

_PREFIXES = sorted([
    "add person", "show person", "show people", "show kin",
    "edit person", "show stash", "bind fragment", "find sources",
    "export gedcom", "import gedcom",
    "tree", "link", "stash", "search", "mode", "skin", "status",
], key=len, reverse=True)

def parse_command(line: str) -> Optional[Command]:
    if not line:
        return None
    m = _TRIGGER.search(line)
    if not m:
        return None
    text = m.group(1).strip()
    lower = text.lower()
    for prefix in _PREFIXES:
        if lower.startswith(prefix):
            rest = text[len(prefix):].strip()
            args = rest.split() if rest else []
            return Command(name=prefix, args=args, raw=text)
    return Command(name="unknown", args=text.split(), raw=text)
