#!/usr/bin/env python3
"""Headless screenshot driver for the SAFE App Store TUI."""
import asyncio
import os

os.environ.setdefault("WILLOW_ALLOW_DEV_GATE", "1")
os.environ.setdefault("WILLOW_DEV_SAFE_ROOT", os.path.expanduser("~/github"))

from tui import StoreApp


async def main() -> None:
    app = StoreApp()
    async with app.run_test(size=(120, 38)) as pilot:
        await pilot.pause()
        # let on_mount build the list
        await pilot.pause(0.3)
        # populate the detail panel with an app that has a manifest
        from textual.widgets import ListView
        lv = app.query_one("#app-list", ListView)
        lv.focus()
        await pilot.pause(0.1)
        target = "vision-board" if any(a["id"] == "vision-board" for a in app._catalog) else app._catalog[0]["id"]
        app._selected = target
        app._show_detail(target)
        await pilot.pause(0.3)
        app.save_screenshot("data/store_tui.svg")
    print("saved data/store_tui.svg")


asyncio.run(main())
