"""Tests for WillowGate enforcement inside the MCP server.

Skips cleanly when willow-gate is not installed (it is an optional,
operator-installed dependency — see gazelle_gate.py).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import willow_gate  # noqa: F401

    _HAVE_GATE = True
except ImportError:
    _HAVE_GATE = False

import case_store
import gazelle_gate
import gazelle_mcp
import gazelle_state


def _call(name: str, arguments: dict | None = None, rid: int = 1) -> dict:
    resp = gazelle_mcp._handle(
        {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
         "params": {"name": name, "arguments": arguments or {}}}
    )
    result = resp["result"]
    text = result["content"][0]["text"]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"raw": text}
    return {"isError": result.get("isError", False), "payload": payload, "text": text}


@unittest.skipUnless(_HAVE_GATE, "willow-gate not installed")
class GateKeeperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        tmp = Path(self._tmpdir)
        self.app_data = tmp / "app"
        self.cases_dir = self.app_data / "cases"
        self.cases_dir.mkdir(parents=True)

        self._patches = [
            mock.patch.dict(
                "os.environ",
                {
                    "GAZELLE_GATE": "1",
                    "WILLOWGATE_DIR": str(tmp / "willowgate"),
                    "WILLOWGATE_REQUIRE_PGP": "0",
                },
            ),
            mock.patch.object(case_store, "APP_DATA", self.app_data),
            mock.patch.object(case_store, "CASES_DIR", self.cases_dir),
            mock.patch.object(gazelle_state, "APP_DATA", self.app_data),
            mock.patch.object(gazelle_state, "STATE_DB", self.app_data / "gazelle_state.db"),
        ]
        for p in self._patches:
            p.start()

        self.keeper = gazelle_gate.GateKeeper()
        self._keeper_patch = mock.patch.object(gazelle_mcp, "_KEEPER", self.keeper)
        self._keeper_patch.start()

        self.secret = "ab" * 32
        self.keeper._gate.register_agent("steady-1", bytes.fromhex(self.secret), max_trust=2)
        self.keeper._gate.register_agent("rookie-1", bytes.fromhex("cd" * 32), max_trust=1)

    def tearDown(self) -> None:
        self._keeper_patch.stop()
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _checkin(self, agent: str = "steady-1", secret: str | None = None,
                 trust: int = 2, tools: list[str] | None = None,
                 pass_count: int = 5) -> dict:
        header = gazelle_gate.build_header(
            agent, secret or self.secret, trust,
            tools if tools is not None else ["read", "write"],
            pass_count=pass_count,
        )
        self._entry = header
        return _call("gazelle_gate_checkin", {"header": header})

    def test_denied_without_checkin(self) -> None:
        out = _call("gazelle_urgent")
        self.assertTrue(out["isError"])
        self.assertIn("gazelle_gate_checkin", out["text"])

    def test_checkin_then_read_and_write(self) -> None:
        out = self._checkin()
        self.assertFalse(out["isError"])
        self.assertTrue(out["payload"]["writable"])

        read = _call("gazelle_urgent")
        self.assertFalse(read["isError"])

        write = _call(
            "gazelle_note",
            {"source_db": "coparent", "item_type": "atom", "item_id": "ATM-001",
             "body": "gated note"},
        )
        self.assertFalse(write["isError"])
        self.assertEqual(write["payload"], {"ok": True, "message": "Note added."})

    def test_rookie_read_only(self) -> None:
        out = self._checkin("rookie-1", "cd" * 32, trust=1, tools=["read"], pass_count=0)
        self.assertFalse(out["isError"])
        self.assertFalse(out["payload"]["writable"])

        self.assertFalse(_call("gazelle_urgent")["isError"])
        denied = _call(
            "gazelle_note",
            {"source_db": "coparent", "item_type": "atom", "item_id": "ATM-001",
             "body": "should not land"},
        )
        self.assertTrue(denied["isError"])
        self.assertIn("DENIED", denied["text"])
        self.assertEqual(gazelle_state.list_notes("coparent", "atom", "ATM-001"), [])

    def test_export_denied_for_rookie(self) -> None:
        self._checkin("rookie-1", "cd" * 32, trust=1, tools=["read"], pass_count=0)
        denied = _call("gazelle_save", {"filename": "x.md", "body": "exfil"})
        self.assertTrue(denied["isError"])

    def test_second_checkin_refused_while_live(self) -> None:
        self._checkin()
        again = self._checkin()
        self.assertTrue(again["isError"])
        self.assertIn("already live", again["text"])

    def test_checkout_closes_session(self) -> None:
        self._checkin()
        _call("gazelle_urgent")
        exit_header = gazelle_gate.build_header(
            "steady-1", self.secret, 2, ["read"],
            pass_count=6, nonce=self._entry["nonce"],
            timestamp=int(self._entry["timestamp"]) + 1000,
        )
        out = _call("gazelle_gate_checkout", {"header": exit_header})
        self.assertFalse(out["isError"])
        self.assertTrue(_call("gazelle_urgent")["isError"])

    def test_forged_trust_refused(self) -> None:
        out = self._checkin("rookie-1", "cd" * 32, trust=4, tools=["read"], pass_count=99)
        self.assertTrue(out["isError"])
        self.assertIn("ceiling", out["text"])

    def test_unknown_tool_denied_when_enabled(self) -> None:
        self._checkin()
        out = _call("gazelle_bogus")
        self.assertTrue(out["isError"])
        self.assertIn("no gate classification", out["text"])

    def test_tools_list_includes_gate_tools(self) -> None:
        resp = gazelle_mcp._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertIn("gazelle_gate_checkin", names)
        self.assertIn("gazelle_gate_checkout", names)


class GateDisabledTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict("os.environ", {"GAZELLE_GATE": "0"})
        self._env.start()
        self._keeper_patch = mock.patch.object(
            gazelle_mcp, "_KEEPER", gazelle_gate.GateKeeper()
        )
        self._keeper_patch.start()

    def tearDown(self) -> None:
        self._keeper_patch.stop()
        self._env.stop()

    def test_calls_pass_through(self) -> None:
        out = _call("gazelle_llm_health")
        self.assertFalse(out["isError"])

    def test_gate_tools_hidden_and_inert(self) -> None:
        resp = gazelle_mcp._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertNotIn("gazelle_gate_checkin", names)
        out = _call("gazelle_gate_checkin", {"header": {}})
        self.assertTrue(out["isError"])


if __name__ == "__main__":
    unittest.main()
