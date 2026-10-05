# gh-NNNNN: Skip VSOCK stream test when the transport reports ENODEV

Target: `3.14` (prepared against tag `v3.14.0`, local branch `gh-vsock-enodev-skip`, commit `007648b`)

## Problem

On a VSOCK guest whose transport cannot reach its own CID (observed on a
Firecracker microVM: `/dev/vsock` present, local CID 3, no loopback transport),
`ThreadedVSOCKSocketStreamTest.testStream` errors instead of skipping:

- client thread: `connect((cid, VSOCKPORT))` → `OSError: [Errno 19] No such device`
- server: `accept()` waits until `LOOPBACK_TIMEOUT` → `TimeoutError`

`HAVE_SOCKET_VSOCK` only checks that the local CID can be read from `/dev/vsock`,
not that a connection can be made. (On 3.9 the same test hangs indefinitely
in `vsock_accept`; it has no accept timeout.)

## Change

`setUp()` first makes one connection attempt to the local CID. If that
fails with `ENODEV`, the test is skipped. Any other result (connection
refused, reset, or success) continues as before.

```diff
     def setUp(self):
+        self.cli = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
+        self.addCleanup(self.cli.close)
+        cid = get_cid()
+        try:
+            self.cli.connect((cid, VSOCKPORT))
+        except OSError as e:
+            if e.errno == errno.ENODEV:
+                self.skipTest(str(e))
         self.serv = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
```

## Constraint: pre-AI code only

Every added line is taken verbatim (leading whitespace aside) from CPython at
`dcb1caef5bd8` (2021-06-28 23:02 +0100). That is the last commit before
GitHub Copilot's technical preview was announced on 2021-06-29. Checked by
`preai_gate.py`, which fails if any added line has no pre-AI origin:

| Added line | Pre-AI origin |
|---|---|
| `self.cli = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)` | `Lib/test/test_socket.py:513` |
| `self.addCleanup(self.cli.close)` | `Lib/test/test_socket.py:514` |
| `cid = get_cid()` | `Lib/test/test_socket.py:515` |
| `try:` | (ubiquitous; first hit `setup.py:16`) |
| `self.cli.connect((cid, VSOCKPORT))` | `Lib/test/test_socket.py:516` |
| `except OSError as e:` | (ubiquitous; first hit `Doc/library/subprocess.rst:1315`) |
| `if e.errno == errno.ENODEV:` | `Lib/test/test_socket.py:2192` (CAN ISOTP bind test) |
| `self.skipTest(str(e))` | `Lib/test/test_c_locale_coercion.py:413` |

Four of the eight lines are the 2021 VSOCK client's own connect sequence,
moved into the server's `setUp()`. The upstream fix on `main`
(gh-145548, March 2026) was deliberately not read while preparing this.

## Verification

| Check | Result |
|---|---|
| `test_socket -m 'ThreadedVSOCKSocketStreamTest*'`, before | ERROR (`ENODEV` + `TimeoutError`) |
| same, after | skipped `'[Errno 19] No such device'`, 3/3 runs |
| full `test_socket`, after | SUCCESS: 745 run, 276 skipped |
| probe removed (mutation) | ERROR returns |
| provenance gate on the diff | 0 lines without pre-AI origin |
| gate with one novel line added (mutation) | fails, exit 1 |

A second guard (`if self.server_crashed: return` in `clientSetUp`) was
tried and dropped. Removing it changed no outcome, so it had no test that
could fail.

## Not verified

- **On a host where VSOCK actually works.** There, the probe connects
  to the local CID before the server binds, and should get a fast refusal
  or reset. Not exercised here: this VM has no working VSOCK transport.
- **When `get_cid()` is `VMADDR_CID_ANY`.** The client remaps that to
  `VMADDR_CID_LOCAL` (gh-119461); the probe uses the raw CID.
- **NEWS entry:** none. A blurb would have to be newly written prose; as a
  test-only change it would need the `skip news` label.

## Disclosure

Prepared by an AI agent (Claude Code). Per the CPython devguide's AI-tools
guidance, disclosure is appreciated. Here the code lines are human-written
2021 CPython code; the selection, placement, commit message and this
description are AI-written.
