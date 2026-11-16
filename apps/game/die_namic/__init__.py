"""die_namic: Die-Namic's core, import-pure and dependency-light.

What Die-Namic adds of its own lives here, with everything it leans on
handed in rather than imported: the core imports nothing from willow, the
store, or the network. The box (apps/game/box) is the host: it finds willow
through its pin and injects willow's pieces, the reader and the ranker,
into the core. The arrow points one way: the host imports the core.

- binder: ask the GM's binder the way willow's own UI searches, over a
  corpus and a ranker handed in (Die-Namic's semantic-search seam).
"""

from .binder import Binder, Found

__all__ = ["Binder", "Found"]
