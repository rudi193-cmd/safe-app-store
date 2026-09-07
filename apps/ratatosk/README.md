# Ratatosk (playground launcher)

Canonical package: [willow-memory/ratatosk](https://github.com/willow-memory/ratatosk)  
PyPI: [`willow-ratatosk`](https://pypi.org/project/willow-ratatosk/)

This directory is the SAFE playground launcher only. The platform runtime ships
from PyPI:

```bash
pip install "willow-ratatosk[mcp,cloud,local]"
pip install -e .
```

Run: `ratatosk --mcp` or `ratatosk --local`

Original playground sources archived at `stores/_ratatosk_extracted/`. `promotion_seam/capabilities.py` stub mirrors the canonical seam for `promote_check` only.
