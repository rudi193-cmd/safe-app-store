import urllib.parse, urllib.request, json
from responder.formatter import result_block, acorn_card

SOURCES = {"familysearch","findagrave","courtlistener","wikipedia","all"}

def cmd_search(args: list) -> str:
    if not args:
        return result_block("search", "Usage: `@squirrel: search [source] query`")
    source = args[0].lower() if args[0].lower() in SOURCES else "all"
    query_args = args[1:] if source != "all" else args
    name = " ".join(query_args)
    if not name:
        return result_block("search", "Provide a name to search.")
    cards = []
    enc = urllib.parse.quote_plus

    if source in ("all", "wikipedia"):
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(name.replace(' ','_'))}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            if data.get("extract"):
                cards.append(acorn_card("wikipedia", data["title"],
                    data["extract"][:280] + "…",
                    url=data.get("content_urls",{}).get("desktop",{}).get("page")))
        except Exception:
            pass

    if source in ("all","familysearch") and name:
        p = name.split()
        url = f"https://www.familysearch.org/search/record/results?q.givenName={enc(p[0])}&q.surname={enc(p[-1])}"
        cards.append(acorn_card("familysearch", f"Search: {name}", "World's largest genealogy database.", url=url))

    if source in ("all","findagrave") and name:
        p = name.split()
        url = f"https://www.findagrave.com/memorial/search?firstname={enc(p[0])}&lastname={enc(p[-1])}"
        cards.append(acorn_card("findagrave", f"Search: {name}", "Memorial and burial records.", url=url))

    if source in ("all","courtlistener") and name:
        url = f"https://www.courtlistener.com/?q={enc(name)}&type=p&order_by=score+desc"
        cards.append(acorn_card("courtlistener", f"Search: {name}", "Federal court records.", url=url))

    if not cards:
        return result_block("search", f"No results for `{name}`")
    return result_block(f"search — {name}", "\n".join(cards))
