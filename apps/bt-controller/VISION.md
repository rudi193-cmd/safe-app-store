# VISION — Sideband

**Product brief · bt-controller → full product**
**Status:** Design/strategy document. No implementation implied by this file.
**Seed:** `bt_daemon.py` — a WSL daemon that owns a Realtek USB adapter at the HCI level, bypasses the Windows Bluetooth stack, and exposes a local WebSocket to a minimal web UI.

---

## 1. The Core Insight

Windows Bluetooth is a black box that fails silently. Devices drop, re-pairing loops forever, audio profiles fight each other, and the Settings UI offers exactly two verbs: *Add device* and *Remove device*. When it breaks — and for millions of users it breaks weekly — there is no diagnostic surface, no logs, no retry policy, no scripting hook. You reboot and pray.

Meanwhile, the hardware underneath is fine. The HCI protocol is open, well-documented, and fully capable. The failure is the *stack*, not the *radio*.

The seed daemon proves the unlock: **detach the radio from the OS stack and own it directly.** Once you speak HCI to the adapter yourself, Bluetooth stops being a mystery and becomes infrastructure — observable, scriptable, automatable, reliable. That's not a bug-fix; it's a category. The same move that gave developers `curl` instead of a browser, or `ffmpeg` instead of a media player, applies to the 2.4 GHz radio sitting in everyone's USB port.

**The job to be done:** *"Make my Bluetooth devices behave like wired ones — always connected, instantly diagnosable, controllable from code."*

### Who it's for

| Segment | Pain today | What they'd pay for |
|---|---|---|
| **Power users / devs on Windows** (primary wedge) | Flaky audio, dropped mice/keyboards, unpairable devices, zero visibility | Reliability + a real control surface |
| **Home-automation tinkerers** | BLE sensors/locks/lights need Home Assistant or hand-rolled Python; Windows is a dead zone for BLE automation | Scriptable BLE with a stable API and event bus |
| **Hardware/firmware engineers & QA teams** | HCI sniffing needs Wireshark + Ubertooth or vendor tools costing $10k+ | Affordable packet-level visibility and repeatable test automation |
| **Fleet operators (kiosks, POS, labs, conference rooms)** | BT peripherals across dozens of machines fail invisibly until a human complains | Remote monitoring, auto-heal, alerts |
| **AI agents** (emerging) | No safe, structured way for an agent to touch local radio hardware | A permissioned MCP surface for the physical world |

The wedge is the first segment — the person who has rebooted three times this week because their headphones won't connect. Everyone else grows out of the same daemon.

---

## 2. Name & Positioning

### Name: **Sideband**

In radio engineering, a sideband carries the real signal alongside the carrier. Sideband runs *alongside* your OS — a parallel, trustworthy channel to your radio hardware. It's evocative, ownable, technical without being alienating, and honest about the architecture (we don't replace Windows Bluetooth for everything; we run beside it and take over what matters).

Sub-brand naming: **Sideband Daemon** (core), **Sideband Deck** (UI), **Sideband Flows** (automation), **Sideband Scope** (diagnostics/sniffer), **Sideband Fleet** (multi-machine).

### One-line pitch

> **"Bluetooth that actually works — and does what you tell it."**

Longer form: *Sideband takes direct control of your Bluetooth radio, bypassing the flaky OS stack, and gives you a rock-solid connection manager, a diagnostic console, and a scripting API for every BT/BLE device you own.*

### Positioning statement

For power users and engineers whose Bluetooth devices misbehave, Sideband is a **local-first radio control plane** that — unlike the built-in OS stack (opaque, unfixable) and unlike dev libraries like bleak/noble (code-only, no product) — delivers reliability you can *see*, connections that *heal themselves*, and a control surface you can *script*.

---

## 3. Full Feature Set (the product it grows into)

The seed daemon already has the right bones: adapter ownership, scan/connect/disconnect, keepalive with exponential-backoff reconnect, a WebSocket API, and a status surface. The product grows along four axes: **reliability, visibility, automation, and scale.**

### 3.1 Core: the Reliability Engine (the daemon, grown up)

- **Adapter abstraction layer.** Today: one Realtek RTL8761B via usbipd/WSL. Grows to: any USB dongle (Realtek, CSR, Intel, Broadcom), multiple simultaneous adapters, and a native Windows driver path (WinUSB/libusb via Zadig, later a signed filter driver) that removes the WSL requirement entirely — this is the single biggest onboarding unlock.
- **Connection profiles per device.** Keepalive interval, reconnect policy, connection priority, preferred PHY/connection parameters, "hold this connection at all costs" mode for mice/keyboards/headphones.
- **Classic BT support, not just BLE.** A2DP/HFP audio routing, HID for input devices, SPP for serial gadgets. Audio is where Windows hurts the most; owning A2DP is the killer reliability demo ("my headphones have not dropped once in 30 days").
- **Pairing vault.** Encrypted local store of link keys/LTKs — pairings survive reinstalls, roam across your machines (via optional sync), and can be exported/imported. Includes migration: *import your existing Windows pairings* so day one isn't a re-pair-everything day.
- **Coexistence manager.** Cleanly claim/release adapters, detect conflicts with the Windows stack, one-click "give this adapter back to Windows."
- **Self-healing watchdog.** The daemon supervises itself: USB re-enumeration on adapter wedge, automatic usbipd re-attach, crash-loop recovery, health heartbeat.

### 3.2 Sideband Deck: the control surface

- **Device dashboard.** Every device with live RSSI sparkline, battery level (GATT battery service), connection uptime, last-seen, profile in use, per-device signal-quality history.
- **Radio environment view.** A live map of the 2.4 GHz neighborhood: advertisers, RSSI over time, channel congestion, "who is that unknown device that appears every night at 9pm?"
- **GATT explorer.** Browse services/characteristics of any BLE device, read/write/subscribe with a UI, decode standard characteristics (battery, heart rate, environmental sensing) automatically, hex + parsed views for the rest.
- **Timeline & event log.** Every connect, drop, retry, and pairing event on a scrubbable timeline — the "flight recorder" that Windows never gave you. When something breaks at 3pm, you can see *why*.
- **Notification & tray presence.** Native tray icon, toast on device drop/recover, quick actions (reconnect all, scan, mute alerts).

### 3.3 Sideband Flows: automation & scripting

- **Event bus.** Every radio event (device seen, RSSI crossed threshold, battery low, connection dropped, characteristic changed) published on WebSocket + MQTT + webhooks.
- **Rules engine.** If-this-then-that for the radio layer: *"When my phone's beacon RSSI > -60, unlock the screen." "When headphone battery < 15%, toast me." "Every night at 2am, power-cycle the adapter and reconnect the sensor mesh." "If the conference-room speaker drops, reconnect and post to Slack."*
- **First-class CLI.** `sb scan`, `sb connect <name|mac>`, `sb watch --json`, `sb gatt read <device> <char>` — pipeable JSON everywhere. The CLI *is* marketing for this audience.
- **SDKs & API.** Stable local REST + WebSocket API (versioned), Python/JS client libraries, PowerShell module.
- **MCP server.** Expose the radio to AI agents as structured tools (`bt_scan`, `bt_connect`, `bt_read_sensor`, `bt_event_subscribe`) with a human-consent permission model per device class. "Claude, my headphones are acting up — fix them" becomes a real sentence. This is native territory for the SAFE App Store, and almost nobody else can offer *hardware* to agents safely.
- **Integrations.** Home Assistant (Sideband as a BLE proxy/bridge on Windows — a genuinely unserved niche), Node-RED nodes, Stream Deck plugin, OBS integration (auto-switch audio when headset connects).

### 3.4 Sideband Scope: diagnostics & engineering (the pro tier)

- **HCI packet capture.** Live capture of HCI traffic to pcap/btsnoop, streamable into Wireshark, with an in-app decoder for the common 90%.
- **Advertisement analyzer.** Decode manufacturer data, iBeacon/Eddystone, and known formats (Xiaomi, Govee, Victron, RuuviTag…) automatically.
- **Connection forensics.** When a link drops, Scope shows the actual reason code, the RSSI at time of death, retry history, and a plain-English diagnosis ("supervision timeout — device likely left range or is sleeping aggressively").
- **Scripted test harness.** Repeatable device test suites: connect/disconnect N times, measure latency distributions, throughput tests, range walk-tests with RSSI logging. Firmware teams pay real money for this; today the alternatives are $10k Ellisys/Frontline boxes or duct-taped scripts.
- **Interference report.** Channel-map analysis, AFH visibility, "your Wi-Fi and your mouse are fighting over channel 39" findings.

### 3.5 Sideband Fleet: multi-machine (the business tier)

- **Fleet console.** All daemons across an office/lab/kiosk-fleet report to one dashboard (self-hosted or cloud): device inventory, health, drop rates, battery levels, firmware versions.
- **Remote remediation.** Reconnect/repair/power-cycle remotely; scheduled maintenance windows; auto-heal policies pushed fleet-wide.
- **Alerting.** Slack/Teams/PagerDuty when the demo room's speaker or the warehouse scanner goes dark — *before* a human notices.
- **Config as code.** Device policies and pairing sets defined in versioned YAML, deployed by MDM/Ansible/Intune.

### 3.6 Platform reach (order matters)

1. **Windows-native daemon** (kill the WSL requirement) — the mass-market gate.
2. **Linux** (nearly free — the daemon's home turf; positions Sideband as *the* BlueZ alternative UX).
3. **Headless/SBC builds** (Raspberry Pi as a Sideband satellite node — extends Fleet's radio coverage cheaply).
4. **macOS** (constrained by Apple's stack; ship a reduced "Deck + Flows over CoreBluetooth" mode, full power via USB adapter where possible).

---

## 4. Key User Journeys

### Journey A — "My headphones keep dropping" (the wedge, 10 minutes to wow)

1. Maya, a developer, searches "windows bluetooth keeps disconnecting," finds Sideband via a Reddit thread.
2. Installer detects her USB adapter, walks her through claiming it (one guided click; the usbipd incantation from the seed's docstring is now invisible plumbing).
3. Deck opens; she pairs her headphones once. Sideband imports her other Windows pairings.
4. She enables **Hold mode** on the headphones. Sideband keeps the link warm, reconnects in under a second on any drop, and shows a 30-day uptime badge.
5. Two weeks later she opens the Timeline out of curiosity, sees that her microwave kills RSSI every lunchtime, moves her dongle to a front port, and becomes the person who evangelizes Sideband in the office Slack. **Aha moment: the first time a device reconnects itself before she noticed it dropped.**

### Journey B — "Script my sensors" (the builder)

1. Tomas has six BLE temperature sensors and a Windows mini-PC. Home Assistant's Windows BLE story is dead ends.
2. `sb scan --json` finds them; the advertisement analyzer identifies them as Xiaomi LYWSD03 and decodes readings with zero config.
3. He writes a Flow: publish every reading to MQTT → Home Assistant picks them up. Ten lines of YAML, no Python.
4. Later he adds a rule: presence detection from his phone's RSSI drives his desk lights. His Windows box is now a first-class BLE hub — a thing that did not exist before.

### Journey C — "Ship the firmware" (the professional)

1. A hardware startup's QA lead needs to prove their new wearable survives 1,000 connect cycles across three adapter chipsets.
2. She writes a Scope test suite (YAML + CLI), runs it overnight on three Sideband nodes, and gets latency histograms, failure reason-codes, and full btsnoop captures for the 4 failures.
3. The captures go straight to the firmware team in Wireshark. What used to need a $12k sniffer and a week of setup took an afternoon and a Pro license.

### Journey D — "The conference rooms just work" (the fleet buyer)

1. An IT manager with 40 conference rooms is drowning in "the speaker won't connect" tickets.
2. Sideband daemons deploy via Intune; Fleet shows every room's audio device health on one screen.
3. Auto-heal policy: on drop, reconnect; on triple-failure, power-cycle adapter; on continued failure, open a ticket *with the diagnostic timeline attached*.
4. Ticket volume drops 80%; the renewal is a formality.

### Journey E — "Agent, handle it" (the frontier)

1. A user tells their desktop AI agent: "my mouse keeps stuttering."
2. The agent, via Sideband's MCP server (scoped, consented per device class), reads the timeline, sees supervision timeouts correlated with 2.4 GHz congestion, switches the mouse's connection parameters, and reports what it did.
3. The radio layer becomes something agents can *perceive and act on* — safely, because Sideband's permission model was designed for exactly this.

---

## 5. Differentiation & Defensibility

**Why this wins, and why it's hard to copy:**

1. **Structural moat: nobody owns this layer.** Microsoft won't expose HCI (support surface they don't want); vendor utilities are chipset-marketing shovelware; dev libraries (bleak, noble, SimpleBLE) are code-only components with no product, no UI, no reliability engine. Sideband sits in a gap that is *structurally* unoccupied: too low-level for consumer software companies, too product-shaped for open-source libraries.
2. **The compatibility corpus compounds.** Every adapter quirk handled (the seed already hardcodes one VID/PID and its usbipd ritual), every device's decoded advertisement format, every reconnect edge case becomes an entry in a knowledge base competitors must independently rediscover. Telemetry-fed (opt-in) device fingerprinting makes the product measurably better with each user — a data moat in a hardware-quirks domain where quirks are the whole game.
3. **Reliability reputation is slow to build and slow to lose.** The product's core promise is trust ("it just stays connected"). That is earned in public — uptime badges, Reddit threads, benchmark posts — and cannot be fast-followed with a feature checklist.
4. **The event bus becomes an ecosystem.** Once Flows, Home Assistant bridges, Stream Deck plugins, and MCP agents depend on Sideband's API, switching costs are real. The API is the platform; the daemon is the beachhead.
5. **Agent-native head start.** A permissioned MCP surface for local radio hardware is a genuinely new category. Being *the* way agents touch Bluetooth is a first-mover position with standards-shaping upside — and it aligns exactly with the SAFE consent model this app already ships (`safe_consent: data_local: true, data_cloud: false`).
6. **Local-first as a trust position.** Radio data is presence data — who's home, when you sleep, where your phone is. "Everything stays on your machine unless you explicitly sync" is both an ethical stance and a differentiator against any cloud-first copycat.

**What is *not* defensible:** the raw technique. usbipd + pyusb + bleak is public knowledge. The moat is the corpus, the polish, the ecosystem, and the trust — which is why speed to a lovable free tier matters more than patents.

---

## 6. Business Model

**Open-core, local-first, priced on depth not on lock-in.**

| Tier | Price | What's included | Who |
|---|---|---|---|
| **Free (open source)** | $0 | Daemon, CLI, basic Deck (dashboard, scan/connect, keepalive/Hold mode), local API. Genuinely useful forever. | The wedge user; the funnel; the community that files adapter-quirk reports |
| **Pro** | $59/yr or $99 lifetime-ish ("perpetual + 1yr updates") | Scope (HCI capture, forensics, test harness), Flows rules engine, advertisement decoder library, pairing-vault sync across personal machines, priority support | Tinkerers, indie hardware devs, the person who got burned once and never wants to debug blind again |
| **Team** | $15/seat/mo | Everything in Pro + shared device policies, config-as-code, small-fleet console (≤25 nodes), Slack alerts | Hardware startups, QA labs, AV-heavy small offices |
| **Fleet/Enterprise** | from $6/node/mo, self-hosted option | Full Fleet console, MDM deployment, SSO, auto-heal policies, SLA support, air-gapped licensing | IT orgs, kiosk/POS operators, labs |
| **Adjacent revenue** | — | Certified adapter program ("Works with Sideband" dongle, possibly white-labeled hardware with margin); paid Home Assistant add-on listing; MCP marketplace positioning | Later; hardware margin funds free tier |

**Model logic:** individuals anchor the brand and the compatibility corpus (free/Pro); the money is in Team/Fleet, where Bluetooth failure has a measurable ticket-cost. Local-first means low COGS — cloud sync and Fleet console are the only hosted components, and both offer self-hosted variants to keep the trust position intact.

**Honest sizing:** this is a $5–30M ARR niche-platform business, not a unicorn path — unless the agent-hardware-interface angle (§5.5) becomes a standard, in which case the ceiling changes. Plan for the former; keep optionality on the latter.

---

## 7. Phased Roadmap

### Phase 0 — Prove the pain is shared (now → 3 months) · *"The daemon, hardened"*
- Harden the seed: proper HCI ownership (BlueZ mgmt API in WSL rather than bleak-over-whatever-stack-is-present), multi-adapter, Classic BT basics, pairing vault v0.
- Guided setup that hides the usbipd ritual; supervisor/watchdog.
- Ship CLI with JSON output. Publish as open source.
- **Gate to Phase 1:** 1,000 GitHub stars or 500 weekly-active daemons; ≥30% of onboarded users still running the daemon at day 30.

### Phase 1 — The lovable product (months 3–9) · *"Deck"*
- Windows-native adapter path (WinUSB) — delete the WSL requirement.
- Deck v1: dashboard, timeline/flight-recorder, GATT explorer, tray + toasts, Hold mode with uptime badge.
- Pairing import from Windows registry. Audio (A2DP) reliability as the hero demo.
- Opt-in telemetry → compatibility corpus begins.
- **Gate:** NPS-style "would you be disappointed if it went away?" ≥ 40% among weekly actives.

### Phase 2 — The platform (months 9–18) · *"Flows + Pro"*
- Event bus (WS/MQTT/webhooks), rules engine, Home Assistant bridge, Stream Deck plugin.
- Scope v1 (HCI capture → Wireshark, forensics, decoder library). **Pro tier launches — first revenue.**
- MCP server with per-device-class consent. Linux build.
- **Gate:** $20k MRR-equivalent from Pro; ≥3 community-built integrations we didn't write.

### Phase 3 — The business (months 18–30) · *"Fleet"*
- Fleet console (hosted + self-hosted), MDM deployment, auto-heal policies, alerting integrations.
- Scripted test harness matures into the QA product; case studies with 2–3 hardware companies.
- Raspberry Pi satellite nodes. Team/Fleet tiers launch.
- **Gate:** 10 paying teams; one fleet deal >100 nodes.

### Phase 4 — The standard (30+ months) · *"The radio control plane"*
- Certified adapter program / branded dongle.
- Agent ecosystem: Sideband as the reference implementation for consent-gated hardware access by AI agents; propose the permission model as a public spec.
- Explore adjacent radios under the same control-plane UX: Zigbee/Thread dongles, maybe SDR-lite. Sideband stops meaning "Bluetooth app" and starts meaning "your machine's radios, under your command."

---

## 8. Risks & Open Questions

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Onboarding friction kills the funnel.** usbipd/WSL/driver-swapping is brutal for the mass wedge user; Zadig-style driver replacement scares people and breaks the Windows stack for that adapter. | **High** — this is the existential risk | Phase 1's native path is the top priority; guided setup with automatic rollback ("give adapter back to Windows" must be one click and bulletproof); recommend a $15 known-good second dongle so users never risk their built-in radio |
| **Microsoft fixes Bluetooth.** A great Win12 BT stack shrinks the wedge. | Medium-low (20 years of evidence says slowly, if ever) | The scripting/diagnostics/fleet/agent layers are valuable even atop a *good* stack; reposition from "bypass" to "control plane" is already built into the brand |
| **Driver signing & Windows kernel politics.** A filter driver needs EV cert + WHQL; user-mode paths (WinUSB) have limits for Classic BT audio latency. | Medium | Stay user-mode as long as possible; budget for signing when audio demands it; the WSL path remains the escape hatch |
| **Adapter chaos.** Chipset quirks (the seed supports exactly one VID/PID) could drown a small team in support. | Medium | Certified-adapter list from day one; the compatibility corpus turns this risk into the moat; community quirk reports triaged in public |
| **Audio is hard.** A2DP/HFP done badly is worse than Windows. Shipping mediocre audio would poison the reliability brand. | Medium-high | Don't ship audio until it beats the OS in blind testing; lead with HID + BLE where the bar is lower and wins are quick |
| **Security surface.** A daemon with radio control + local WebSocket (the seed's port 8421 has no auth) is an attack target; pairing vault holds keys. | High (reputational) | Auth on the local API from Phase 0 (token handshake, origin checks), encrypted vault, third-party audit before Pro launch, responsible-disclosure program. The SAFE consent framing is an asset here — lean into it |
| **Open-core cannibalization.** If free is too good, Pro doesn't convert; too crippled, community dies. | Medium | Free = reliability for *your* devices; paid = visibility, automation depth, and multi-machine. Reliability is never paywalled — that's the brand |
| **Presence-data privacy.** The radio-environment view sees neighbors' devices; fleet telemetry sees employee presence. | Medium | Local-first defaults, aggressive anonymization in telemetry, explicit fleet-mode disclosures; publish a plain-language data policy early |

### Open questions

1. **Which second segment first?** Home-automation (community energy, low willingness-to-pay) vs. QA/engineering (high willingness-to-pay, slower community)? The Phase 2 gate should force this choice with data.
2. **How far into audio do we go?** Owning A2DP is the biggest wow and the biggest engineering swamp (codecs, latency, licensing for aptX/LDAC). Possible middle path: own the *connection* and hand the stream to Windows — is that technically coherent?
3. **Lifetime license vs. subscription for Pro?** This audience hates subscriptions; lifetime caps revenue. "Perpetual + 1 year of updates" (JetBrains model) is the current bet — validate it.
4. **Is the MCP/agent surface a feature or the company?** If agent-hardware access becomes a real category, Sideband could pivot from "Bluetooth product with an MCP server" to "the consent layer between agents and local hardware." Watch the signal; don't chase it prematurely.
5. **Do we build/brand hardware?** A certified dongle solves adapter chaos and adds margin, but hardware ops are a different company. Threshold: revisit when support tickets attributable to adapter quirks exceed 25%.
6. **Windows Store / winget distribution vs. direct?** Store gives reach and trust; direct preserves margin and the driver-level installer freedom we may need.
7. **Relationship to the SAFE App Store ecosystem:** does Sideband stay a flagship SAFE app (consent-model showcase, agent-accessible hardware exemplar) or spin out standalone? Both are viable; the consent model should be shared either way.

---

## 9. Summary

Sideband turns a one-adapter WSL daemon into the missing control plane for personal radio hardware. It wedges in on the sharpest consumer pain on the platform ("Windows Bluetooth is broken"), earns trust with visible, self-healing reliability, then grows along the natural gradient of its own API: automation for builders, forensics for engineers, fleets for businesses, and a consent-gated hardware surface for AI agents. The technique is public; the moat is the compatibility corpus, the reliability reputation, and the ecosystem that forms around the event bus. Ambition, grounded: a durable $10M+ ARR platform business with a real option on becoming the standard for how software — human-driven or agent-driven — touches the radios around us.

*ΔΣ=42*
