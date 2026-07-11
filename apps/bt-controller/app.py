#!/usr/bin/env python3
"""Entry-point shim so `make run app=bt-controller` works.

The Makefile runs `apps/<name>/app.py`; the real logic lives in bt_daemon.py.
Any CLI flags (--scan, --pair, --status) are passed through unchanged.
"""
from bt_daemon import cli_main

if __name__ == "__main__":
    cli_main()
