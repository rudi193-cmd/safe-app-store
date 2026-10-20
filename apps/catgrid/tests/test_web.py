"""The page: one file, built from the engine and the Python's own data, and
committed as built (a stale page is the browser playing yesterday's rules)."""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "catgrid" / "web"
spec = importlib.util.spec_from_file_location("catgrid_web_build", WEB / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class TestThePage(unittest.TestCase):
    def test_the_committed_page_is_the_built_page(self):
        self.assertEqual((WEB / "catgrid.html").read_text(encoding="utf-8"), build.render(),
                         "catgrid.html is stale: run python3 catgrid/web/build.py")

    def test_the_page_carries_napkins_and_no_trivia_corpus(self):
        page = build.render()
        data = json.loads(re.search(r"var CATGRID_DATA = (\{.*?\});\n", page).group(1))
        self.assertEqual(set(data), {"words", "words_why", "bank_why", "smallest", "largest"})
        self.assertIn("stays with Jeles", data["bank_why"])
        self.assertNotIn("corpus/seed", page)

    def test_the_engine_is_inlined_without_its_module_tail(self):
        page = build.render()
        self.assertIn("function generate(seed, n, k, tries)", page)
        self.assertNotIn("module.exports", page)
        self.assertNotIn("/* ENGINE */", page)


if __name__ == "__main__":
    unittest.main()
