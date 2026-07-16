import db.fragments as fragments_db
from responder.formatter import result_block


def parse_stash_args(args: list) -> dict:
    result = {"confidence": "uncertain", "fragment_type": "story"}
    text_parts = []
    i = 0

    def take_value(j):
        # A flag value is ONE token unless quoted. The dispatcher space-splits,
        # so a quoted multi-word value arrives as several tokens — consume until
        # the token that closes the quote. Unquoted stays a single token, so a
        # flag can never greedily swallow the story text that follows it
        # (e.g. `--person Oscar Mann kept letters` → person "Oscar", not the
        # whole sentence). Quote multi-word values: `--person "Oscar Mann"`.
        if j >= len(args):
            return "", j
        if args[j][:1] not in ('"', "'"):
            return args[j], j + 1
        q = args[j][0]
        vals = []
        while j < len(args):
            vals.append(args[j]); j += 1
            if vals[-1].endswith(q) and (len(vals) > 1 or len(vals[-1]) > 1):
                break
        return " ".join(vals).strip('"').strip("'"), j

    while i < len(args):
        a = args[i]
        if a == "--confidence" and i + 1 < len(args):
            result["confidence"] = args[i + 1]; i += 2
        elif a == "--type" and i + 1 < len(args):
            result["fragment_type"] = args[i + 1]; i += 2
        elif a == "--source":
            result["source"], i = take_value(i + 1)
        elif a == "--person":
            result["person_name"], i = take_value(i + 1)
        else:
            text_parts.append(a); i += 1
    result["story_text"] = " ".join(text_parts).strip('"')
    return result


def cmd_stash(conn, args: list) -> str:
    if not args:
        return result_block("stash", "Usage: `@squirrel: stash \"text\" "
                            "[--person \"Name\"] [--confidence likely]`")
    kwargs = parse_stash_args(args)
    story = kwargs.pop("story_text", "")
    # B-004: an explicit --person wins; the first-two-words heuristic is only a
    # fallback for when the fragment text happens to lead with the name.
    person_name = kwargs.pop("person_name", "") or ""
    if not person_name:
        words = story.split()
        person_name = " ".join(words[:2]) if len(words) >= 2 else story
    frag = fragments_db.add_fragment(conn, person_name=person_name, story_text=story, **kwargs)
    return result_block("stash",
        f"✓ Fragment {frag['id']} stashed for **{person_name}**\n"
        f"  `{story[:80]}`\n  confidence: `{frag['confidence']}`")


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
        status, payload = persons_db.resolve_person(conn, person_query)
        if status == "none":
            return result_block("bind fragment", f"No person found: `{person_query}`")
        if status == "ambiguous":
            from responder.formatter import did_you_mean
            return result_block("bind fragment", did_you_mean(person_query, payload)
                                + "\n\n_Then bind by the exact name._")
        person = payload
        from binder import Binder
        Binder(conn).bind(frag_id, person["id"])
        return result_block("bind fragment", f"✓ Fragment {frag_id} bound to **{person['full_name']}**")
    elif args and args[0] == "all":
        from binder import Binder
        r = Binder(conn).auto_bind()
        if r.get("note"):
            return result_block("bind all", f"Nothing to bind — {r['note']}.")
        lines = [f"✓ Bound {len(r['bound'])} of {r['examined']} examined fragment(s)."]
        if r["ambiguous"]:
            lines.append(f"⚠ {r['ambiguous']} skipped as ambiguous (a tie between "
                         "similarly-named people — bind those by ID).")
        if r["remaining"]:
            lines.append(f"… {r['remaining']} not yet examined (work budget) — "
                         "run `bind fragment all` again to continue.")
        return result_block("bind all", "\n".join(lines))
    else:
        return result_block("bind fragment",
            "Usage: `@squirrel: bind fragment ID → Person Name`\nOr: `@squirrel: bind fragment all`")
