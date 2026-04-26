import db.fragments as fragments_db
from responder.formatter import result_block


def parse_stash_args(args: list) -> dict:
    result = {"confidence": "uncertain", "fragment_type": "story"}
    text_parts = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--confidence" and i + 1 < len(args):
            result["confidence"] = args[i + 1]; i += 2
        elif a == "--source" and i + 1 < len(args):
            result["source"] = args[i + 1]; i += 2
        elif a == "--type" and i + 1 < len(args):
            result["fragment_type"] = args[i + 1]; i += 2
        else:
            text_parts.append(a); i += 1
    result["story_text"] = " ".join(text_parts).strip('"')
    return result


def cmd_stash(conn, args: list) -> str:
    if not args:
        return result_block("stash", "Usage: `@squirrel: stash \"text\" --confidence likely`")
    kwargs = parse_stash_args(args)
    story = kwargs.pop("story_text", "")
    words = story.split()
    person_name = " ".join(words[:2]) if len(words) >= 2 else story
    frag = fragments_db.add_fragment(conn, person_name=person_name, story_text=story, **kwargs)
    return result_block("stash",
        f"✓ Fragment {frag['id']} stashed\n  `{story[:80]}`\n  confidence: `{frag['confidence']}`")


def cmd_show_stash(conn, args: list) -> str:
    frags = fragments_db.get_unsynced_fragments(conn, limit=20)
    if not frags:
        return result_block("stash", "Stash is empty (or all fragments have been bound).")
    lines = [f"**{len(frags)} unsynced fragments:**\n"]
    for f in frags:
        preview = (f.get("story_text") or "")[:60]
        lines.append(f"  [{f['id']}] `{f['confidence']}` — {f['person_name']} — {preview}")
    return result_block("stash", "\n".join(lines))


def cmd_bind_fragment(conn, args: list) -> str:
    raw = " ".join(args)
    sep = "→" if "→" in raw else ("->" if "->" in raw else None)
    if sep:
        parts = raw.split(sep, 1)
        try:
            frag_id = int(parts[0].strip())
        except ValueError:
            return result_block("bind fragment", f"Expected numeric fragment ID before `{sep}`")
        person_query = parts[1].strip()
        import db.persons as persons_db
        matches = persons_db.search_persons(conn, person_query)
        if not matches:
            return result_block("bind fragment", f"No person found: `{person_query}`")
        from binder import Binder
        Binder(conn).bind(frag_id, matches[0]["id"])
        return result_block("bind fragment", f"✓ Fragment {frag_id} bound to **{matches[0]['full_name']}**")
    elif args and args[0] == "all":
        from binder import Binder
        results = Binder(conn).auto_bind()
        return result_block("bind all", f"✓ Auto-bound {len(results)} fragment(s)")
    else:
        return result_block("bind fragment",
            "Usage: `@squirrel: bind fragment ID → Person Name`\nOr: `@squirrel: bind fragment all`")
