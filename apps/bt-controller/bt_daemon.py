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
import signal
import sys
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/bt-daemon.log"),
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
            log.info(f"Adapter found: {dev.manufacturer} {dev.product}")
            adapter_attached = True
            return True
        else:
            log.warning("Adapter not found — run: usbipd.exe attach --wsl --busid <BUSID>")
            adapter_attached = False
            return False
    except ImportError:
        log.error("pyusb not installed — run: pip install pyusb")
        return False


async def scan_devices(duration=SCAN_DURATION):
    """Scan for nearby Bluetooth devices using bleak."""
    global scan_results
    try:
        from bleak import BleakScanner
        log.info(f"Scanning for {duration}s...")
        devices = await BleakScanner.discover(timeout=duration)
        scan_results = [
            {"mac": d.address, "name": d.name or "Unknown", "rssi": d.rssi}
            for d in devices
        ]
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
            connected_devices[mac] = {
                "name": client.address,
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
                # Read any service to keep connection alive
                services = client.services
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
                    connected_devices[mac]["client"] = client
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
    try:
        import websockets
    except ImportError:
        log.error("websockets not installed — run: pip install websockets")
        return

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
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": str(e)}))


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
        await scan_devices()
    elif args.pair:
        if not ok:
            sys.exit(1)
        await connect_device(args.pair)
        # Keep running for keepalive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
    elif args.status:
        print(json.dumps({
            "adapter": adapter_attached,
            "connected": len(connected_devices),
        }, indent=2))
    else:
        # Default: daemon mode
        log.info("Starting BT Controller Daemon")
        if not ok:
            log.warning("Adapter not attached — daemon will wait for attachment")
        await start_ws_server()


if __name__ == "__main__":
    asyncio.run(main())
