# BT Controller

Bluetooth device manager that bypasses the Windows Bluetooth stack. Two independent halves:

1. **`bt_daemon.py`** — a Python daemon that runs in WSL and owns a Realtek RTL8761B USB adapter
   (VID `0BDA`, PID `C821`) directly, using BLE via [bleak](https://github.com/hbldh/bleak).
   It exposes a JSON WebSocket API on `ws://localhost:8421` and a small CLI.
2. **`web/index.html`** — a static web UI that uses the browser's **Web Bluetooth** API
   (Chrome/Edge) to scan, connect, keep-alive, and reconnect devices. It currently manages
   connections through the browser itself and does **not** talk to the daemon's WebSocket yet.

Use the daemon when you want connections owned by WSL/Linux instead of Windows; use the web UI
when the browser's Bluetooth stack is good enough.

## Prerequisites

### Windows side (USB passthrough to WSL)

```powershell
winget install usbipd

usbipd list                          # find the Realtek adapter (VID:PID 0bda:c821)
usbipd bind --busid <BUSID>          # one-time: allow sharing (admin shell)
usbipd attach --wsl --busid <BUSID>  # pass the adapter into WSL (re-run after replug)
```

### WSL side

```bash
sudo apt install linux-tools-generic hwdata libusb-1.0-0
pip install -r requirements.txt      # pyusb, bleak, websockets
```

bleak on Linux talks to BlueZ over D-Bus, so `bluetoothd` must be running and the adapter
visible (`hciconfig` / `bluetoothctl list`). Requires **Python 3.9+** and **bleak >= 0.22**
(the scan code uses the `AdvertisementData` API).

## Install / Run (from repo root)

```bash
make install app=bt-controller
make run app=bt-controller        # starts the daemon (WebSocket on :8421)
```

Or directly:

```bash
cd apps/bt-controller
python3 bt_daemon.py              # daemon mode (default)
```

## CLI

| Command | What it does |
|---|---|
| `python3 bt_daemon.py` | Run the daemon: checks the adapter, serves `ws://localhost:8421`. |
| `python3 bt_daemon.py --daemon` | Same as above, explicit. |
| `python3 bt_daemon.py --scan` | BLE scan (~10 s), print results as JSON, exit. Exits 1 if the adapter is missing. |
| `python3 bt_daemon.py --pair <MAC>` | Connect to a device and hold the connection with keep-alive pings; exits 1 if the connection is lost permanently. |
| `python3 bt_daemon.py --status` | Query the **running daemon** over the WebSocket and print its live status. Falls back to a local adapter check (`daemon_running: false`) if no daemon is reachable. |

Logs go to stderr and to `$BT_DAEMON_LOG` (default: `<tmpdir>/bt-daemon.log`).

## WebSocket protocol (`ws://localhost:8421`)

Send one JSON object per message with an `action` field; the daemon replies with one JSON object.

### `scan`
```json
{"action": "scan", "duration": 10}
```
Reply — devices sorted by RSSI (strongest first):
```json
{"type": "scan_results", "devices": [{"mac": "AA:BB:CC:DD:EE:FF", "name": "PYLE Speaker", "rssi": -42}]}
```

### `connect`
```json
{"action": "connect", "mac": "AA:BB:CC:DD:EE:FF"}
```
Reply: `{"type": "connect_result", "mac": "...", "success": true}`
On success the daemon starts a keep-alive loop (GATT read every 15 s, up to 5 reconnect
attempts with linear backoff before giving up).

### `disconnect`
```json
{"action": "disconnect", "mac": "AA:BB:CC:DD:EE:FF"}
```
Reply: `{"type": "disconnected", "mac": "..."}`

### `status`
```json
{"action": "status"}
```
Reply:
```json
{
  "type": "status",
  "adapter": true,
  "connected": {"AA:BB:CC:DD:EE:FF": {"name": "...", "connected_at": "...", "keepalive": true}},
  "scan_results": [...]
}
```

Unknown actions or malformed JSON return `{"type": "error", "message": "..."}`.

## Web UI

Open `web/index.html` in Chrome or Edge (Web Bluetooth requires a secure context: `https://`
or `http://localhost` — the `file://` scheme generally works for `requestDevice` in Chrome, but
serving it locally is more reliable):

```bash
cd apps/bt-controller/web && python3 -m http.server 8422
# then browse to http://localhost:8422/
```

Features: scan (general / audio-filtered / permissive), connect, battery-level read,
per-device keep-alive with automatic reconnect (5 attempts, linear backoff), and a live log.
The UI is also deployable as a static Cloudflare Pages site (`wrangler.toml`).

## Known limitations

- The web UI uses the browser's Bluetooth stack; it is not yet wired to the daemon's
  WebSocket API. Bridging the two is the next step.
- "Pairing" is BLE GATT connection only — classic Bluetooth (A2DP audio routing) is out of scope.
- The daemon's keep-alive reads the first readable GATT characteristic it finds; devices
  exposing none will rely on the connection state check alone.
