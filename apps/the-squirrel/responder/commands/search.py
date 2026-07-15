"""External search — deep links only, by design.

The app never touches an outside socket. Every card is a link with the
name embedded; the user's click is the egress AND the consent for it —
request and confirm stay separate authorities, and the confirm is a human
finger. (Wikipedia used to be a live fetch; demoted 2026-07-15 to make
this invariant total.) The standing switch is consent.online.
"""
import urllib.parse
from responder.formatter import result_block, acorn_card
from sap.core import consent

SOURCES = {"familysearch", "findagrave", "courtlistener", "wikipedia", "all"}

_OFFLINE_NOTE = ("_Online lookups are off. Flip **ONLINE** on the Privacy "
                 "page to show links to outside archives._")


def cmd_search(args: list) -> str:
    if not args:
        return result_block("search", "Usage: `@squirrel: search [source] query`")
    source = args[0].lower() if args[0].lower() in SOURCES else "all"
    query_args = args[1:] if source != "all" else args
    name = " ".join(query_args)
    if not name:
        return result_block("search", "Provide a name to search.")
    if not consent.online():
        return result_block("search", _OFFLINE_NOTE)
    cards = []
    enc = urllib.parse.quote_plus

    if source in ("all", "wikipedia"):
        url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(name.replace(' ', '_'))}"
        cards.append(acorn_card("wikipedia", f"Look up: {name}",
                                "Encyclopedia entry, if one exists.", url=url))

    if source in ("all", "familysearch") and name:
        p = name.split()
        url = f"https://www.familysearch.org/search/record/results?q.givenName={enc(p[0])}&q.surname={enc(p[-1])}"
        cards.append(acorn_card("familysearch", f"Search: {name}", "World's largest genealogy database.", url=url))

    if source in ("all", "findagrave") and name:
        p = name.split()
        url = f"https://www.findagrave.com/memorial/search?firstname={enc(p[0])}&lastname={enc(p[-1])}"
        cards.append(acorn_card("findagrave", f"Search: {name}", "Memorial and burial records.", url=url))

    if source in ("all", "courtlistener") and name:
        url = f"https://www.courtlistener.com/?q={enc(name)}&type=p&order_by=score+desc"
        cards.append(acorn_card("courtlistener", f"Search: {name}", "Federal court records.", url=url))

    if not cards:
        return result_block("search", f"No results for `{name}`")
    return result_block(f"search — {name}", "\n".join(cards))
