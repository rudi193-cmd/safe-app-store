# BT Controller — Product Vision

*Status: strategy / design exercise. No implementation implied by this document.*

---

## 1. The Core Insight

Windows Bluetooth is a black box that lies to you. It says "connected" while audio stutters. It silently drops keyboards and controllers when the machine sleeps. It gives you no visibility into signal strength, no scriptable control, no way to force a reconnect without diving into Device Manager and re-pairing from scratch. Power users — developers, streamers, musicians, IoT tinkerers, competitive gamers — feel this pain weekly and have no recourse except folklore fixes ("uninstall the driver, reboot, re-pair").

The daemon that exists today proves the sharp end of the wedge: talk to the Realtek adapter at the HCI level, skip the Windows stack, and give the user a keepalive loop that actually holds a connection open. That's a hack for one adapter on one platform. The product opportunity is bigger: **Bluetooth as an observable, scriptable, reliable subsystem — the way `iptables` made networking legible, or the way Wireshark made "the network is slow" into "here is exactly which packet stalled."**

**Who it's for:** people who treat their computer as an instrument, not an appliance — developers building BLE integrations, esports and rhythm-game players who cannot tolerate input lag or dropped controllers, musicians running BLE MIDI, streamers juggling wireless mics/earbuds/capture gear, IoT hobbyists prototyping against real hardware, and IT-adjacent power users tired of babysitting dongles for coworkers.

**The job it does:** "Let me see, and control, exactly what my Bluetooth radio is doing — and never lose a connection I care about without knowing why."

---

## 2. Product Name & Positioning

**Name:** **Wavecraft** *(working name; alt candidates: Radiograph, Signalsmith, HCI Console)*

**One-line pitch:**
> Wavecraft is the mission-control panel for Bluetooth that Windows should have shipped — direct radio access, live diagnostics, and scriptable automation for the devices you can't afford to have drop.

**Positioning statement:**
For power users who rely on wireless peripherals for work, performance, or play, Wavecraft is a Bluetooth control layer that bypasses the flaky native stack and exposes the radio directly — unlike Windows Settings or generic Bluetooth managers, Wavecraft gives you live signal telemetry, forced keepalive, scriptable device policies, and an audit trail of every disconnect, so "why did my headset just cut out mid-call" becomes a five-second lookup instead of a shrug.

---

## 3. The Full Feature Set (Beyond the Daemon)

### 3.1 Radio & Connection Layer
- **Multi-adapter support**: any HCI-capable USB dongle (Realtek, Broadcom, CSR, Intel), not just one VID/PID. Adapter auto-detection with a compatibility database crowdsourced from users.
- **Native Linux/macOS support** as first-class targets, not just a WSL workaround — WSL becomes one supported "bridge mode" for Windows users, not the whole architecture.
- **Direct HCI + BLE + Classic (BR/EDR) support**: today's daemon is BLE-only via bleak; a real product needs Classic profiles too (A2DP for audio, HID for keyboards/mice/controllers) since those are the devices that hurt most when dropped.
- **Connection policies per device**: "always reconnect," "reconnect only on Wi-Fi presence," "never auto-reconnect (avoid stealing pairing slots)," "priority tier" for multi-device conflicts (e.g., don't let a fitness band's reconnect attempts starve a headset).
- **Signal & link-quality telemetry**: live RSSI graphs, packet loss estimates, latency histograms, channel-hop visualization — the "Wireshark for BT" layer.
- **Interference diagnostics**: detect 2.4GHz Wi-Fi channel overlap and USB3 port interference (a well-known Realtek/BT killer), and suggest fixes (move dongle, change Wi-Fi channel).

### 3.2 Automation & Scripting
- **CLI + REST/WebSocket API** (the current WS port grows into a documented, versioned API) for scripting device state from any language.
- **Rules engine**: "when device X connects, mute system output for 2s" (fixes the classic Bluetooth pairing chime); "if RSSI < -80 for 30s, notify"; "disconnect device Y whenever device Z connects" (exclusive audio routing).
- **Macro/profile switching**: one click (or `wavecraft profile game-night`) to reconfigure which devices are prioritized, which keepalive policies apply, which audio device is default.
- **Home Assistant / Stream Deck / OBS plugins**: expose device state and actions as integrations for the automation tools power users already run.

### 3.3 Visibility & Trust
- **Persistent connection history & audit log**: every connect/disconnect/reconnect with timestamp, RSSI at time of drop, and a best-guess reason (radio interference vs. driver timeout vs. device battery vs. explicit user action). This turns "it just disconnected" into a diagnosable event.
- **Device fingerprint library**: known profiles for common problem devices (specific headset models, specific controller chipsets) with community-sourced fixes ("this Sony WH-1000XM4 firmware has a known reconnect bug — apply workaround").
- **Health dashboard**: adapter uptime, reconnect success rate, per-device reliability score over time.

### 3.4 Multi-Device & Team Features
- **Device groups**: manage a whole desk's worth of peripherals (headset, mouse, keyboard, controller, mic) as one coordinated set.
- **Fleet mode** (see monetization): sysadmins/IT managing Bluetooth peripherals across many machines in a lab, studio, or shared workspace — think conference rooms full of flaky BT speakers.
- **Shareable device profiles**: export a known-good config for a specific headset/dongle combo and share it, or import one from the community library.

### 3.5 Platform & Ecosystem
- **Companion mobile app** for iOS/Android to monitor and control the desktop radio remotely (useful for streamers/musicians who want a phone-based "kill switch" or quick reconnect without alt-tabbing).
- **Plugin SDK**: let advanced users write device-specific handlers (custom GATT service parsers, vendor-specific keepalive quirks) without touching daemon internals.
- **Self-hosted or local-only by default** (privacy story below), with an optional cloud sync tier for cross-machine profile sync and community data sharing.

---

## 4. Key User Journeys

### Journey A — "My headset keeps cutting out during calls" (the wedge use case)
1. User installs Wavecraft, plugs in a supported dongle (or Wavecraft flags their existing Windows-managed adapter as unreliable and prompts a USB dongle purchase link/recommendation).
2. Wavecraft scans, finds the headset, and shows a live RSSI graph — the user immediately sees the signal dips corresponding to their call drops.
3. Wavecraft flags interference: "Your headset's channel overlaps with your Wi-Fi router's 2.4GHz band." Suggests moving the dongle to a front-panel USB2 port (fixes USB3-BT interference, a real, common issue) or changing Wi-Fi channel.
4. User enables Keepalive + Auto-Reconnect policy for that device. Drops become reconnects logged in history instead of dead air.
5. User checks the health dashboard a week later: reconnect success rate 98%, zero manual re-pairs. They tell a friend.

### Journey B — "I want my controller to reconnect instantly when I sit down to game"
1. User defines a rule: "when device `Xbox Controller` is powered and in range, auto-connect and set as priority HID device."
2. They bind this to a Stream Deck button labeled "Game Mode" that also mutes notification audio and disconnects a competing BT speaker.
3. One press, everything is in the right state — no Windows Settings spelunking.

### Journey C — "I'm building a BLE integration and Windows Bluetooth is fighting me"
1. Developer installs the CLI, runs `wavecraft scan --json`, pipes output into their own tooling.
2. They use the REST API to script pairing/unpairing as part of an automated test suite for their own IoT product.
3. Wavecraft's raw HCI access lets them see GATT-level detail Windows normally hides, cutting their debug time from hours to minutes.

### Journey D — "I manage BT peripherals for a shared studio/lab"
1. IT admin installs Fleet mode across five machines.
2. Central dashboard shows adapter/device health across all of them; admin pushes a device profile ("known-good config for our studio's wireless mics") to all machines at once.
3. Weekly digest email: "Room 3's dongle had 40 reconnects this week — likely faulty USB port."

---

## 5. What Makes It Defensible / Differentiated

- **Depth over breadth**: generic Bluetooth managers (and Windows itself) treat BT as "connected/not connected." Wavecraft treats it as an observable radio system with telemetry, history, and policy — a genuinely different product category, closer to a network diagnostic tool than a settings panel.
- **Device-quirk knowledge base**: the real moat is accumulated, crowdsourced knowledge about *which specific devices/chipsets misbehave and how to fix them*. This compounds — every user who reports a fixed issue makes the product better for the next person with that exact headset. Hard to replicate without the install base.
- **Cross-platform HCI abstraction**: building (and maintaining) a clean abstraction over HCI/BLE/Classic across Realtek/Broadcom/Intel/CSR chipsets on Windows(WSL)/Linux/macOS is genuinely hard, unglamorous systems work. That's a real technical moat, not just UI polish.
- **Trust through transparency**: local-first, no cloud dependency for core function, open audit log of what the daemon does to the radio. Power users are exactly the segment most suspicious of "yet another background service" — winning their trust with radical transparency (open logs, optional open-source core) is a differentiator competitors chasing consumer mass-market wouldn't bother with.
- **Automation surface**: the CLI/API/rules-engine turns Wavecraft into infrastructure other tools plug into (Stream Deck, Home Assistant, CI pipelines for IoT devs) — this creates switching cost and an ecosystem, not just a utility you open once to fix a problem.

---

## 6. Monetization / Business Model

**Core product stays free and local-first** — this is a trust-and-adoption requirement for the target audience (power users despise anything that smells like BT telemetry-as-spyware). Monetize the layers on top:

| Tier | Price | Includes |
|---|---|---|
| **Free** | $0 | Single machine, single adapter, manual reconnect, basic scan/connect/disconnect, local history (7 days) |
| **Pro** | ~$6–9/mo or $59/yr | Full telemetry & interference diagnostics, unlimited history, rules engine, CLI/API access, device-quirk KB access, cloud profile sync across the user's own machines |
| **Studio/Team** | ~$15–25/user/mo | Fleet mode (multi-machine dashboard), shared device profiles, admin alerts, priority support — targets studios, esports orgs, dev shops, IT departments |
| **Enterprise** | Custom | SSO, on-prem/self-hosted fleet server, SLA, custom device certification for hardware vendors |

**Secondary revenue streams:**
- **Hardware affiliate/bundle**: curated "known-good" USB BT dongle recommendations (affiliate revenue), eventually a co-branded/private-label dongle once the compatibility database proves demand.
- **Vendor partnerships**: headset/peripheral makers pay for "Wavecraft Certified" compatibility badges and priority quirk-fix support — turns the crowdsourced pain database into a channel for hardware vendors who want fewer support tickets.
- **API/SDK licensing**: IoT companies embed Wavecraft's HCI abstraction layer in their own device-setup tooling.

**Why people pay:** the free tier solves the acute pain (my thing keeps disconnecting); the paid tier sells *time and certainty* — diagnostics that save debugging hours, automation that removes repeated manual fiddling, and fleet tools that save an IT admin from visiting five desks.

---

## 7. Phased Roadmap

**Phase 0 — Today (seed):** WSL-only daemon, one Realtek adapter, BLE scan/connect/keepalive, minimal WebSocket + Web Bluetooth UI. Proves the core mechanic: bypass the flaky stack, hold the connection.

**Phase 1 — Harden the wedge (0–3 months):**
- Broaden adapter support beyond one VID/PID (Realtek family, Broadcom, CSR).
- Add Classic BT profile support (A2DP, HID) — this is where the real pain (headsets, controllers) lives, not just BLE.
- Ship connection history/audit log and a basic RSSI graph — turn "it disconnected" into "here's why."
- Native installer/packaging so non-technical power users don't need to hand-roll WSL/usbipd setup.

**Phase 2 — Make it a system, not a script (3–9 months):**
- Rules engine + CLI + documented REST/WS API.
- Interference diagnostics and the device-quirk knowledge base (seed it manually, then crowdsource).
- Native Linux and macOS builds, not just Windows/WSL.
- Free/Pro tier split ships here — telemetry depth and rules engine become the paywall.

**Phase 3 — Ecosystem (9–18 months):**
- Stream Deck / Home Assistant / OBS integrations.
- Mobile companion app.
- Plugin SDK for community device handlers.
- Fleet mode beta for studios/small IT teams.

**Phase 4 — Platform (18+ months):**
- Vendor certification program ("Wavecraft Certified" compatibility badge).
- Enterprise fleet server, SSO, on-prem deployment.
- Explore becoming the reference open diagnostic layer that hardware vendors integrate against directly (the "Wireshark of Bluetooth" endgame) — potentially open-sourcing the core HCI engine to accelerate this while keeping the dashboard/fleet/cloud layers commercial.

---

## 8. Risks & Open Questions

**Technical risks:**
- HCI-level access typically requires elevated privileges (raw sockets, driver-level hooks) — Windows makes this substantially harder than Linux; the WSL/usbipd bridge is a workaround with real fragility (USB passthrough breaks on sleep/resume, driver updates, VM reboots). A true native-Windows low-level path may require a signed kernel driver, which is a much bigger engineering and trust commitment.
- Chipset fragmentation is real: Realtek, Broadcom, CSR, Intel, and various dongles all have different HCI quirks. "Support more adapters" is not a checkbox, it's ongoing driver-whisperer work — could become an unbounded support burden.
- Classic Bluetooth (A2DP/HID) is harder to control at a low level than BLE — codec negotiation, SCO/audio routing, and coexistence with the OS's own driver (you may not be able to fully "bypass" the stack for audio profiles the way BLE keepalive does).

**Market/positioning risks:**
- Is the market big enough? "Power users annoyed by Bluetooth" may be a passionate but small niche — need to validate willingness to pay vs. expecting a free utility (this space is full of beloved free open-source tools like `bluetoothctl`/BlueZ front-ends).
- Windows could simply fix its Bluetooth stack (or Microsoft could ship better diagnostics natively), eroding the core wedge — mitigated somewhat by the depth/automation/fleet layers being differentiated regardless, but the "bypass Windows" pitch has a shelf life.
- Security/privacy perception: a tool that talks directly to radio hardware and (optionally) syncs to the cloud will draw scrutiny from the exact security-conscious audience it targets. Needs a credible security story (ideally open-source core) from day one, not retrofitted.

**Business model risks:**
- Local-first + free core makes monetization harder than SaaS-native competitors; Pro tier value (telemetry, rules engine) must be compelling enough that power users — a notoriously price-resistant, self-hosting-inclined audience — actually convert.
- Vendor certification revenue depends on reaching install-base scale first; chicken-and-egg with the crowdsourced quirk database.

**Open questions to resolve before committing further investment:**
1. Does a native (non-WSL) low-level Windows path exist without a kernel driver, or is a signed driver unavoidable for the full vision?
2. What fraction of the target pain is BLE vs. Classic (audio/HID)? This determines whether Phase 1's Classic-profile work is the real priority or a nice-to-have.
3. Would the target audience actually pay, or does this stay a beloved free tool (fine outcome, but changes the business model entirely toward sponsorship/donations/open-core)?
4. Is "bypass Windows entirely" the right long-term frame, or should the product reposition as "the diagnostic/automation layer on top of whatever BT stack you have" (broader addressable market, less confrontational with Microsoft, works even without HCI-level bypass)?
