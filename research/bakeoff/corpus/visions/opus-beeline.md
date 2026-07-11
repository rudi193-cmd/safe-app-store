# BT Controller — Product Vision

> *"The OS treats Bluetooth as an appliance. Power users need it as an instrument."*

**Status:** Seed → Product Vision
**Seed today:** A Python daemon (`bt_daemon.py`) that runs in WSL, claims a Realtek RTL8761B USB adapter at the HCI level via `usbipd`, bypasses the Windows Bluetooth stack entirely, and exposes a local WebSocket (`ws://localhost:8421`) to a minimal web UI. A parallel browser-side path uses the Web Bluetooth API directly. One sharp pain solved: **Windows Bluetooth is flaky, and there is no scriptable, direct, honest control layer underneath it.**

---

## 1. The Core Insight

Every desktop OS ships Bluetooth as a black box. When it works, it's invisible. When it doesn't — a headset that pairs but won't route audio, a controller that drops every 90 seconds, a device that "connected successfully" but exposes nothing — the user is handed a spinner and a *"Try removing the device and adding it again."* There is no ground truth, no log, no lever.

The insight: **the flakiness isn't Bluetooth's fault — it's the abstraction's fault.** The radio and the HCI protocol underneath are deterministic and inspectable. The vendor driver stack sitting on top hides the state machine, swallows errors, and makes policy decisions (idle timeouts, power management, profile negotiation) that the user can neither see nor override.

BT Controller's thesis: **own the adapter beneath the OS driver, expose the real state machine, and give the user direct, scriptable, observable control.** Once you own the radio, "fixing flaky Bluetooth" is just the first feature. You've actually built a *Bluetooth workbench* — a place where connections are objects you can inspect, automate, script, and reason about.

The seed already contains the whole thesis in miniature: it detaches the adapter from Windows, drives HCI directly, keeps devices alive with an explicit keepalive loop, and surfaces every event to a log. The product is what happens when that pattern is made robust, cross-platform, multi-adapter, and programmable.

## 2. Who It's For

Three concentric rings, expanding outward over the roadmap:

**Ring 1 — The frustrated power user (beachhead).** WSL/Windows developers, homelabbers, retro-gaming and emulation enthusiasts, people running audio gear off cheap BT dongles. They already tolerate `usbipd` incantations. They want their headset/controller/keyboard to *just stay connected* and to see *why* when it doesn't. This is who the seed serves today.

**Ring 2 — The BLE builder.** Firmware and IoT developers, makers, security researchers, students. They need a reliable, scriptable GATT client that doesn't fight them: reproducible scans, raw characteristic read/write/notify, connection logs they can diff, automation they can commit to a repo. Today they cobble this together from `bleak`, `nRF Connect`, `gatttool`, and a wall of `hcitool` snippets.

**Ring 3 — The operator at scale.** Test labs, QA benches, kiosk/retail/signage fleets, and anyone maintaining rooms full of BT peripherals. They need *many* adapters and *many* devices managed as inventory, with health monitoring, alerting, and remote control. This is where a hobby tool becomes infrastructure.

The job, stated as the user would: **"Give me direct, reliable, scriptable control over my Bluetooth devices — and tell me the truth about what they're doing."**

## 3. Product Name & Positioning

**Name:** **BeeLine** — *your Bluetooth, direct.*
(Working title. "BT Controller" is the honest engineering name; "BeeLine" is the product name — it captures *directness* — a bee line to the device, bypassing the stack — and the *BT/BLE* pun. The catalog `app_id` stays `bt-controller` per the SAPS1 rule that app_id = directory name.)

**One-line pitch:**
> **BeeLine takes Bluetooth away from your flaky OS driver and hands you the wheel — direct HCI control, rock-solid connections, and every device scriptable.**

**Category positioning:** Not a driver, not a settings panel. A **Bluetooth control plane** — the layer between the radio and your intent.

**Positioning against the alternatives:**
- **vs. the OS Bluetooth settings:** BeeLine shows you the state machine and lets you override it. The OS hides both.
- **vs. `nRF Connect` / vendor apps:** Those are read-heavy inspection tools tied to one ecosystem. BeeLine is cross-platform, owns the adapter, and is built for *persistent, automated* control, not one-off pokes.
- **vs. raw `bleak`/`hcitool` scripts:** BeeLine is the productized, observable, resilient version — the difference between a shell alias and a tool.

## 4. The Full Feature Set

The seed is the kernel. Here is the product it grows into, grouped by capability layer.

### 4.1 Connection Reliability (the wedge — harden what exists)
- **Adaptive keepalive** — the seed's fixed 15s GATT ping becomes per-device-learned. BeeLine profiles each device's true idle-disconnect threshold and pings just under it, minimizing radio traffic and battery drain.
- **Reconnect intelligence** — replace naive linear backoff with jittered exponential backoff, RSSI-gated retries (don't burn attempts when the device is out of range), and "wait for presence" mode (reconnect the instant the device reappears in a passive scan, rather than polling).
- **Connection recipes** — save a device's full working config (services to hold open, MTU, connection interval, keepalive cadence) as a named profile that survives reboots and moves between machines.
- **Drop forensics** — every disconnect is captured with cause where derivable (supervision timeout, out-of-range, peer-initiated, adapter reset), not just a counter. The seed's `stat-drops` becomes a queryable event log.

### 4.2 Device Workbench (make connections into objects)
- **GATT explorer** — full service/characteristic/descriptor tree, live notifications, raw and typed read/write. Decode common characteristics (battery, HID report maps, heart rate, device info) and let users define custom decoders.
- **Live signal & telemetry** — RSSI graphs over time, TX power, connection interval, latency, throughput. Turn "it feels laggy" into a chart.
- **Device identity & memory** — BeeLine remembers every device it has ever seen: friendly names, tags, notes, last-seen, pairing keys. A personal device CMDB.
- **Sniffer-lite** — passive advertising capture and decode (iBeacon, Eddystone, manufacturer data, service UUIDs) for nearby devices without connecting.

### 4.3 Automation & Scripting (the moat — turn control into a platform)
- **Rules engine** — *when* `<trigger>` *do* `<action>`. Triggers: device appears/disappears, RSSI crosses threshold, characteristic value changes, time of day, adapter event. Actions: connect/disconnect, run a recipe, write a characteristic, fire a webhook, run a shell command.
- **CLI & headless mode** — the seed's argparse CLI grows into a first-class `beeline` command: `beeline scan`, `beeline connect <tag>`, `beeline watch <device> --on-drop 'notify-send'`. Scriptable, pipeable, CI-friendly.
- **Local REST + WebSocket API** — the current ad-hoc WS protocol becomes a documented, versioned API so anything (Home Assistant, Node-RED, a bash script, a Stream Deck) can drive BeeLine.
- **Automation library** — shareable, version-controllable automation files (YAML/JSON) checked into a repo. "Keep my controller alive during game sessions" or "log my heart-rate strap to CSV" become a file you download.

### 4.4 Multi-Adapter & Fleet (scale — Ring 3)
- **Adapter manager** — drive *several* USB adapters at once; pin devices to adapters; hot-swap; auto-recover an adapter after a USB reset (the seed's single-adapter check generalizes to a pool).
- **Remote agents** — run a BeeLine agent on a Raspberry Pi or NUC and control its adapters from a central dashboard. The `usbip` pattern generalizes to the network.
- **Fleet dashboard & alerting** — inventory of devices across sites, health status, uptime, alert on drop/low-battery/out-of-range via webhook, email, or push.
- **Audit log** — every connect/disconnect/write, who and when — for lab reproducibility and compliance.

### 4.5 Cross-Platform Reach (remove the WSL ceiling)
- **Native Linux** — direct `hci`/BlueZ path, no WSL indirection.
- **Native Windows** — a signed WinUSB/libusb path so users don't need WSL + usbipd at all; ship the whole experience as one installer.
- **macOS** — Core Bluetooth-backed feature parity where the platform allows (Apple locks HCI harder; positioning shifts to workbench + automation over raw adapter ownership).
- **Web Bluetooth companion** — the existing browser UI stays as the zero-install "try it now" entry point, honest about its sandbox limits.

### 4.6 Experience Layer
- **Unified desktop app** — the current dark-mono web UI is the right aesthetic; it grows into a proper multi-pane cockpit: device list, live workbench, automation editor, log/timeline.
- **Menu-bar / tray mode** — for the "I just want my stuff connected" user, BeeLine lives in the tray, quietly holding connections, surfacing only on trouble.
- **SAFE-native** — stays a first-class SAFE App Store citizen: local-first data (`data_local: true`, `data_cloud: false`), explicit pairing consent, `bluetooth` permission — privacy is a feature, not an afterthought.

## 5. Key User Journeys

**Journey A — "Fix my flaky headset" (Ring 1, day one value).**
User installs BeeLine, clicks *Adopt Adapter* (the wizard replaces the manual `usbipd bind/attach` dance and remembers the busid). Scans, sees their headset, clicks *Connect*, toggles *Keep-Alive → ON*. BeeLine learns the idle threshold, holds the connection, and when a drop happens it silently reconnects and logs why. The user's actual experience: *the headset just works now, and there's a log that proves it.*

**Journey B — "Automate my controller for game night" (Ring 1→2).**
User saves their gamepad as a recipe, then writes a one-line rule: *when controller appears, connect + keepalive; when my emulator process exits, release it.* They commit the automation file to their dotfiles repo. It now follows them to every machine.

**Journey C — "Reverse a BLE gadget" (Ring 2).**
Firmware dev scans, connects, opens the GATT explorer, subscribes to notifications, and watches raw bytes stream as they press buttons on the device. They write a custom decoder, save it, and export a repeatable test script that drives the characteristic and asserts the response — now part of their CI.

**Journey D — "Run the QA bench" (Ring 3).**
Lab tech has 12 test devices across 4 adapters on a shelf NUC running a BeeLine agent. Central dashboard shows all 12 with live RSSI and battery. A rule fires a Slack webhook when any device drops or dips below 20% battery. Every session's connect/write history is auditable for repro.

## 6. What Makes It Defensible

1. **Owning the adapter is a real moat.** The hard, unglamorous engineering — claiming USB adapters across Windows/WSL/Linux, driving HCI robustly, surviving USB resets, learning per-device timing — is exactly what competitors *don't* do because the OS "already handles Bluetooth." That reluctance is the opening.
2. **Reliability compounds into trust.** A tool that keeps your devices connected earns a place in muscle memory. Switching cost is emotional and practical once your automations and device memory live here.
3. **The automation library is a network effect.** Shared, forkable automation and decoder files mean the catalog of "BeeLine does X for device Y" grows with the community, not the core team. Every solved device makes the next user's problem already-solved.
4. **Cross-platform + programmable is a rare combination.** Vendor apps are single-ecosystem and read-only-ish; scripts are power-user-only and fragile. Being *both* approachable *and* deeply scriptable across OSes is defensible surface area.
5. **Local-first / privacy posture.** In a category where "smart" usually means "phones home," BeeLine's SAFE-native, local-only default is a differentiator for exactly the security-conscious users in Rings 2 and 3.
6. **Data gravity.** Device memory, drop forensics, learned timing profiles, and audit logs accumulate. The longer you run BeeLine, the more it knows about *your* radio environment — and that knowledge isn't portable to a competitor.

## 7. Monetization / Business Model

Open core, with value climbing from individual reliability to fleet infrastructure.

- **Free / Open Source (Community).** The daemon, single-adapter control, GATT workbench, CLI, local API, and Web Bluetooth companion. This is the seed, matured. Drives adoption and the automation/decoder library. Building trust here is the whole go-to-market.
- **Pro — one-time license or low monthly (individual power user).** Multi-adapter, rules engine, adaptive keepalive, drop forensics/timeline, saved recipes, native signed Windows/macOS installers, priority device-decoder packs. The "make my Bluetooth life effortless" tier.
- **Team / Fleet — per-seat or per-agent subscription (Ring 3).** Remote agents, central dashboard, fleet alerting, audit logs, SSO, role-based control. This is where recurring revenue lives — labs and operators paying for uptime and observability.
- **Marketplace (later, optional).** Curated, verified device decoders and automation packs; revenue share with contributors. Turns the community moat into a channel.

Guardrails: never paywall *basic reliability* — that's the whole reputation. The free tier must genuinely fix flaky Bluetooth. Monetize *scale, automation depth, and operations*, not the wedge.

## 8. Phased Roadmap

**Phase 0 — Seed (today).** WSL daemon, HCI passthrough, WebSocket UI, keepalive + reconnect, Web Bluetooth path. Proves the thesis on one adapter, one OS path.

**Phase 1 — Harden the Wedge (0–3 mo).** Adapter-adoption wizard (kill the manual usbipd steps), adaptive keepalive, smarter reconnect (jitter, RSSI-gating, presence-wait), drop forensics with causes, saved recipes, persistent device memory. **Goal: "BeeLine reliably keeps my devices connected" is unambiguously true.**

**Phase 2 — The Workbench (3–6 mo).** Full GATT explorer, live RSSI/telemetry charts, advertising sniffer-lite, custom decoders, a real desktop cockpit UI + tray mode. **Goal: win Ring 2 (BLE builders).**

**Phase 3 — Programmable (6–10 mo).** Documented REST + WS API, first-class `beeline` CLI, rules engine, shareable automation files, integrations (Home Assistant, Node-RED, webhooks). **Goal: BeeLine becomes a platform, not an app.**

**Phase 4 — Cross-Platform (9–14 mo).** Native signed Windows (no WSL), native Linux/BlueZ, macOS workbench parity. One installer per OS. **Goal: remove every install-friction ceiling.**

**Phase 5 — Fleet (14–24 mo).** Multi-adapter pools, remote agents, central dashboard, alerting, audit logs, Team tier. **Goal: monetize operators; BeeLine as infrastructure.**

**Phase 6 — Ecosystem (24 mo+).** Decoder/automation marketplace, community verification, revenue share. **Goal: the moat compounds itself.**

## 9. Risks & Open Questions

**Technical**
- **Platform hostility to HCI ownership.** Windows requires signed drivers (WinUSB/libusb) for a no-WSL experience; macOS effectively forbids raw HCI. The adapter-ownership moat is strongest on Linux/WSL and weakest on macOS — does the value prop survive where we can't own the radio?
- **Adapter fragmentation.** The seed hardcodes one Realtek chip (VID `0x0BDA`/PID `0xC821`). Real coverage means a tested compatibility matrix across Realtek/CSR/Broadcom/Intel dongles — a long, unglamorous tail.
- **USB passthrough fragility.** `usbipd` resets, WSL kernel quirks, and USB power management are real reliability hazards *for the tool that promises reliability*. We must be dramatically more robust than the stack we replace.
- **BLE ≠ Classic.** The seed is BLE/GATT-centric (`bleak`). Audio (A2DP/HFP) and Classic HID live in a different, harder world. How much Classic support do we promise, given audio is a top Ring-1 pain?

**Product / Market**
- **Is "flaky Bluetooth" a vitamin or a painkiller?** For some users it's a rare annoyance; for our beachhead it's a recurring rage. Is the acute-pain segment large enough to seed the flywheel?
- **The free tier must be genuinely great, which risks capping conversion.** Where exactly is the Pro line drawn so reliability stays free but the tool still monetizes?
- **Ring 3 is a different company.** Fleet/labs is real revenue but a very different sales motion and product surface. When do we commit, and does it distract from the beloved individual tool?

**Strategic**
- **Platform risk.** If Microsoft/Apple materially fix their BT stacks, the wedge narrows. The workbench + automation + cross-platform value must be strong enough to stand *without* the "OS is broken" premise. (Bet: it is — nobody is building the programmable control plane regardless of stack quality.)
- **Safety/abuse surface.** Direct radio control + sniffing + scripted writes is powerful and dual-use. What are the responsible-disclosure and guardrail commitments, especially for the security-researcher ring?
- **Naming & catalog coherence.** Product name "BeeLine" vs. SAPS1 `app_id: bt-controller` — resolve before any public launch so branding and the store catalog don't diverge.

---

*BeeLine starts by fixing the single most universal, most under-served annoyance in personal computing — Bluetooth that won't behave — and uses the hard-won position beneath the OS driver to grow into the programmable, cross-platform control plane for every Bluetooth device you own or operate.*

ΔΣ=42
