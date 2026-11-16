# decks: Die-Namic's card art, fetched, never committed

The card pages (`ui/play-hearts.html`, `ui/play-crazy-eights.html`,
`ui/play-tarot.html`) draw their own cards. When art has been fetched, they
also offer it: a **Deck** for the faces and a **Back**, each remembered in
that browser.

    python apps/game/decks/fetch_decks.py          # every deck below
    python apps/game/decks/fetch_decks.py knoll    # just one
    python apps/game/decks/fetch_decks.py --list
    python apps/game/ui/build.py                   # then lay the pages again

The art lands in `apps/game/ui/decks/`, which git ignores, with a `deck.json`
for each deck and a `NOTICE.md` for all of them. Running it again fetches
only what's missing.

## The decks, and why each may be here

Die-Namic is to stay Apache-2.0 compatible, so a deck goes in this list only
when its art is public domain or CC0. LGPL decks were looked at and left out
(htdebeer/SVG-cards; Chris Aguilar's cards inside pakastin/deck-of-cards and
cardsJS, whose code is MIT but whose art is not).

| Deck | Kind | By | Licence, as its source states it | From |
|---|---|---|---|---|
| `knoll` | 52 | Byron Knoll, kept by notpeter | "released into the public domain, or optionally licensed under the WTFPL" | github.com/notpeter/Vector-Playing-Cards |
| `tekeye` | 52 + 12 backs | Tek Eye | "placed into the Public Domain… no permission is required" | tekeye.uk/playing_cards/svg-playing-cards |
| `kennard-goodall` | 52 + 2 backs | Adrian Kennard, after Goodall & Son | "Released under CC0 Public Domain licence" | me.uk/cards (his generator, old style) |
| `kennard-fourcolour` | 52 + 2 backs | Adrian Kennard | CC0, as above | me.uk/cards (four colour) |
| `rws1910` | 78 tarot | Pamela Colman Smith, 1909–1910 | public domain: published 1909–1910 (US); Smith died 1951, so life + 70 ended in 2022 (UK, EU) | the 1910 "Pamela-A" scans on Wikimedia Commons |

The tarot is the original printing only. Later recoloured editions carry their
own copyright and trademarks, so nothing here is called "Rider-Waite", and each
card's own Commons page is kept in `rws1910/deck.json`. Kennard's "Alteran"
style is left out (it may need a licence from MGM).

These were picked from samples set side by side on 2026-11-16. A deck that
isn't free to share, however good, doesn't go in this list.
