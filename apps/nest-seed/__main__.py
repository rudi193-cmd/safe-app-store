"""python apps/nest-seed — delegate to app.main()."""
from __future__ import annotations

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from .app import main
except ImportError:
    from app import main


if __name__ == "__main__":
    main()
