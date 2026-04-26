import db.sources as sources_db
from responder.formatter import result_block, acorn_card

def cmd_find_sources(conn, args: list) -> str:
    if not args:
        return result_block("find sources", "Usage: `@squirrel: find sources [query] [--state Iowa] [--provider familysearch]`")
    state = None; provider = None; query_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--state" and i + 1 < len(args):
            state = args[i+1]; i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            provider = args[i+1]; i += 2
        else:
            query_parts.append(args[i]); i += 1
    results = sources_db.lookup_sources(conn, query=" ".join(query_parts),
                                         state=state, provider=provider, limit=8)
    if not results:
        return result_block("find sources", "No sources found.")
    cards = "\n".join(
        acorn_card(r["provider"], r["name"], f"State: {r['state'] or '—'}", url=r["url"])
        for r in results
    )
    return result_block(f"sources ({len(results)} found)", cards)
