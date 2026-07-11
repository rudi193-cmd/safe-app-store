#!/usr/bin/env python3
"""
bt_daemon.py — HCI Bluetooth Controller Daemon
================================================
Owns the Realtek RTL8761B adapter at the HCI protocol level via WSL.
Bypasses the Windows Bluetooth driver entirely.

Prerequisites:
  Windows: winget install usbipd
  WSL:     pip install pyusb bleak
           sudo apt install linux-tools-generic hwdata

  Then attach the adapter:
    usbipd.exe list                    # Find the Realtek (VID 0BDA, PID C821)
    usbipd.exe bind --busid <BUSID>    # Allow sharing
    usbipd.exe attach --wsl --busid <BUSID>  # Pass to WSL

Usage:
  python3 bt_daemon.py              # Start daemon
  python3 bt_daemon.py --scan       # Scan for devices
  python3 bt_daemon.py --pair MAC   # Pair a device
  python3 bt_daemon.py --status     # Show connected devices

Architecture:
  This daemon runs in WSL and talks HCI directly to the USB adapter.
  The safe-app-bt-controller web UI communicates with this daemon
  via a local WebSocket (ws://localhost:8421).

Agent: opus (ENGINEER trust)
System: Willow AIOS
ΔΣ=42
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import datetime

_LOG_PATH = os.environ.get("BT_DAEMON_LOG", os.path.join(tempfile.gettempdir(), "bt-daemon.log"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_PATH),
    ]
)
log = logging.getLogger("bt-daemon")

# ── Config ────────────────────────────────────────────────────────
ADAPTER_VID = 0x0BDA
ADAPTER_PID = 0xC821
WS_PORT = 8421
SCAN_DURATION = 10  # seconds
KEEPALIVE_INTERVAL = 15  # seconds
RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF = 2  # seconds, multiplied by attempt number

# ── State ─────────────────────────────────────────────────────────
connected_devices = {}  # mac -> {name, connected_at, signal, keepalive}
scan_results = []
adapter_attached = False


async def check_adapter():
    """Verify the USB adapter is attached to WSL."""
    global adapter_attached
    try:
        import usb.core
        dev = usb.core.find(idVendor=ADAPTER_VID, idProduct=ADAPTER_PID)
        if dev:
            # Reading string descriptors needs device access and can raise
            # (permissions, langid) even when the device is present.
            try:
                desc = f"{dev.manufacturer} {dev.product}"
            except Exception:
                desc = f"VID:{ADAPTER_VID:04X} PID:{ADAPTER_PID:04X}"
            log.info(f"Adapter found: {desc}")
            adapter_attached = True
            return True
        else:
            log.warning("Adapter not found — run: usbipd.exe attach --wsl --busid <BUSID>")
            adapter_attached = False
            return False
    except ImportError:
        log.error("pyusb not installed — run: pip install pyusb")
        adapter_attached = False
        return False
    except Exception as e:
        # e.g. usb.core.NoBackendError when libusb is missing
        log.error(f"USB check failed: {e}")
        adapter_attached = False
        return False


async def scan_devices(duration=SCAN_DURATION):
    """Scan for nearby Bluetooth devices using bleak."""
    global scan_results
    try:
        from bleak import BleakScanner
        log.info(f"Scanning for {duration}s...")
        # return_adv=True yields {address: (BLEDevice, AdvertisementData)}.
        # RSSI lives on AdvertisementData — BLEDevice.rssi was removed in bleak 0.22.
        found = await BleakScanner.discover(timeout=duration, return_adv=True)
        scan_results = sorted(
            (
                {
                    "mac": device.address,
                    "name": device.name or adv.local_name or "Unknown",
                    "rssi": adv.rssi,
                }
                for device, adv in found.values()
            ),
            key=lambda d: d["rssi"],
            reverse=True,
        )
        log.info(f"Found {len(scan_results)} devices")
        for d in scan_results:
            log.info(f"  {d['mac']} | {d['name']} | RSSI: {d['rssi']}")
        return scan_results
    except ImportError:
        log.error("bleak not installed — run: pip install bleak")
        return []
    except Exception as e:
        log.error(f"Scan failed: {e}")
        return []


async def connect_device(mac: str):
    """Connect to a BLE device and maintain the connection."""
    try:
        from bleak import BleakClient
        log.info(f"Connecting to {mac}...")
        client = BleakClient(mac)
        await client.connect()
        if client.is_connected:
            log.info(f"Connected to {mac}")
            # Prefer the advertised name from the last scan; fall back to the MAC.
            name = next(
                (r["name"] for r in scan_results if r["mac"].upper() == mac.upper()),
                mac,
            )
            connected_devices[mac] = {
                "name": name,
                "connected_at": datetime.now().isoformat(),
                "client": client,
                "keepalive": True,
            }
            # Start keepalive loop
            asyncio.create_task(keepalive_loop(mac, client))
            return True
        return False
    except Exception as e:
        log.error(f"Connection to {mac} failed: {e}")
        return False


async def keepalive_loop(mac: str, client):
    """Ping device periodically to prevent idle disconnect."""
    from bleak import BleakClient
    attempt = 0
    while mac in connected_devices and connected_devices[mac].get("keepalive"):
        await asyncio.sleep(KEEPALIVE_INTERVAL)
        try:
            if client.is_connected:
                # Do real GATT I/O so the link doesn't idle out.
                # (client.services is a cached property — accessing it is not a ping.)
                for service in client.services:
                    for char in service.characteristics:
                        if "read" in char.properties:
                            await client.read_gatt_char(char)
                            break
                    else:
                        continue
                    break
                attempt = 0  # Reset on success
                log.debug(f"Keepalive ping to {mac} OK")
            else:
                raise Exception("Disconnected")
        except Exception:
            attempt += 1
            log.warning(f"Keepalive failed for {mac} (attempt {attempt}/{RECONNECT_ATTEMPTS})")
            if attempt >= RECONNECT_ATTEMPTS:
                log.error(f"Giving up on {mac} after {RECONNECT_ATTEMPTS} attempts")
                connected_devices.pop(mac, None)
                break
            # Reconnect
            delay = RECONNECT_BACKOFF * attempt
            log.info(f"Reconnecting to {mac} in {delay}s...")
            await asyncio.sleep(delay)
            try:
                client = BleakClient(mac)
                await client.connect()
                if client.is_connected:
                    entry = connected_devices.get(mac)
                    if entry is None:
                        # Device was removed while we were reconnecting — undo.
                        await client.disconnect()
                        break
                    entry["client"] = client
                    log.info(f"Reconnected to {mac}")
                    attempt = 0
            except Exception as e:
                log.error(f"Reconnect failed: {e}")


async def disconnect_device(mac: str):
    """Disconnect a device."""
    entry = connected_devices.pop(mac, None)
    if entry and entry.get("client"):
        try:
            await entry["client"].disconnect()
            log.info(f"Disconnected {mac}")
        except Exception:
            pass


# ── WebSocket Server (for safe-app-bt-controller UI) ──────────────

async def ws_handler(websocket):
    """Handle WebSocket messages from the web UI."""
    remote = getattr(websocket, "remote_address", None)
    log.info(f"UI client connected: {remote}")
    async for message in websocket:
        try:
            cmd = json.loads(message)
            action = cmd.get("action", "")

            if action == "scan":
                results = await scan_devices(cmd.get("duration", SCAN_DURATION))
                await websocket.send(json.dumps({"type": "scan_results", "devices": results}))

            elif action == "connect":
                mac = cmd.get("mac", "")
                ok = await connect_device(mac)
                await websocket.send(json.dumps({"type": "connect_result", "mac": mac, "success": ok}))

            elif action == "disconnect":
                mac = cmd.get("mac", "")
                await disconnect_device(mac)
                await websocket.send(json.dumps({"type": "disconnected", "mac": mac}))

            elif action == "status":
                status = {
                    "type": "status",
                    "adapter": adapter_attached,
                    "connected": {
                        mac: {"name": d.get("name"), "connected_at": d.get("connected_at"), "keepalive": d.get("keepalive")}
                        for mac, d in connected_devices.items()
                    },
                    "scan_results": scan_results,
                }
                await websocket.send(json.dumps(status))

            else:
                await websocket.send(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))

        except json.JSONDecodeError:
            await _ws_send_safe(websocket, {"type": "error", "message": "Invalid JSON"})
        except Exception as e:
            log.error(f"WS command failed: {e}")
            await _ws_send_safe(websocket, {"type": "error", "message": str(e)})
    log.info(f"UI client disconnected: {remote}")


async def _ws_send_safe(websocket, payload: dict):
    """Send a JSON payload, ignoring a connection that closed mid-reply."""
    try:
        await websocket.send(json.dumps(payload))
    except Exception:
        pass


async def start_ws_server():
    """Start WebSocket server for UI communication."""
    try:
        import websockets
        server = await websockets.serve(ws_handler, "localhost", WS_PORT)
        log.info(f"WebSocket server on ws://localhost:{WS_PORT}")
        await server.wait_closed()
    except ImportError:
        log.error("websockets not installed — daemon runs without UI connection")
        # Keep running for CLI usage
        while True:
            await asyncio.sleep(3600)


async def query_daemon_status(timeout: float = 5.0):
    """Ask a running daemon for its status over the WebSocket.

    Returns the parsed status dict, or None if no daemon is reachable.
    """
    try:
        import websockets
        async with websockets.connect(
            f"ws://localhost:{WS_PORT}", open_timeout=timeout
        ) as ws:
            await ws.send(json.dumps({"action": "status"}))
            reply = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.loads(reply)
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="HCI Bluetooth Controller Daemon")
    parser.add_argument("--scan", action="store_true", help="Scan for devices and exit")
    parser.add_argument("--pair", metavar="MAC", help="Connect to a device by MAC")
    parser.add_argument("--status", action="store_true", help="Show adapter status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon with WebSocket server")
    args = parser.parse_args()

    # Always check adapter first
    ok = await check_adapter()

    if args.scan:
        if not ok:
            sys.exit(1)
        results = await scan_devices()
        print(json.dumps(results, indent=2))
    elif args.pair:
        if not ok:
            sys.exit(1)
        if not await connect_device(args.pair):
            sys.exit(1)
        # Keep running for keepalive
        while args.pair in connected_devices:
            await asyncio.sleep(1)
        log.error(f"Lost {args.pair} permanently — exiting")
        sys.exit(1)
    elif args.status:
        # Real state lives in the running daemon, not this fresh process —
        # query it over the WebSocket; fall back to a local adapter check.
        status = await query_daemon_status()
        if status is not None:
            status["daemon_running"] = True
            print(json.dumps(status, indent=2))
        else:
            print(json.dumps({
                "daemon_running": False,
                "adapter": adapter_attached,
                "connected": {},
                "note": f"No daemon reachable on ws://localhost:{WS_PORT}",
            }, indent=2))
    else:
        # Default: daemon mode
        log.info("Starting BT Controller Daemon")
        if not ok:
            log.warning("Adapter not attached — daemon will wait for attachment")
        await start_ws_server()


def cli_main():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down")


if __name__ == "__main__":
    cli_main()
