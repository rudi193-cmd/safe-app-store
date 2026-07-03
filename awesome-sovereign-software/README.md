# Awesome Sovereign Software [![Awesome](https://awesome.re/badge.svg)](https://awesome.re)

> Software you own. Apps that run without accounts, servers, or subscriptions — and keep working when the company doesn't.

Most "local-first" lists are about the technology — sync engines, CRDTs, databases for developers.
This list is about **finished applications you can install today** that pass a strict, stated test
for user sovereignty. If the vendor vanished tomorrow, everything on this list would still work.

For the developer-tooling side of local-first, see the [related lists](#related-lists) at the bottom.

## The Sovereignty Test

Every entry must pass **all five**:

1. **Runs without an account.** No sign-up, login, or activation to use the core features.
2. **Runs without a server.** Core function works entirely on your device. Optional sync is fine
   only if it is truly optional and user-controlled (your storage, your keys, or end-to-end encrypted).
   Apps that require hosting a server belong on [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted), not here.
3. **No subscription for core function.** Free or pay-once. Nothing expires.
4. **Your data is readable without the app.** Stored locally in an open or documented format
   (plain text, Markdown, SQLite, standard media…), or with first-class export.
5. **Survives the vendor.** If the project's website and company disappeared today, the installed
   app would keep working indefinitely.

Open source is strongly preferred. Proprietary software is admitted only when the data format is
fully open and everything else passes — and it is always marked.

## Legend

- `LICENSE` — software license (proprietary entries marked `Proprietary`)
- 📄 — data lives in plain files you can open anywhere (Markdown, text, CSV…)
- 🗃️ — data lives in an open database format (SQLite, KDBX…)
- 📵 — fully offline; core app never needs the network
- 🔁 — optional sync, user-controlled or end-to-end encrypted

## Contents

- [Notes & Knowledge](#notes--knowledge)
- [Tasks & Productivity](#tasks--productivity)
- [Finance](#finance)
- [Passwords & Secrets](#passwords--secrets)
- [Files, Sync & Backup](#files-sync--backup)
- [Maps & Navigation](#maps--navigation)
- [Reading & Media](#reading--media)
- [Drawing & Diagrams](#drawing--diagrams)
- [Photos](#photos)
- [Learning](#learning)
- [Local AI](#local-ai)
- [Messaging](#messaging)
- [Documents & Office](#documents--office)
- [Suites & Stores](#suites--stores)
- [Building Sovereign Software](#building-sovereign-software)
- [Papers & Research](#papers--research)
- [Related Lists](#related-lists)

## Notes & Knowledge

- [Obsidian](https://obsidian.md/) `Proprietary` 📄 — Markdown knowledge base over a folder of plain-text files on your disk. Huge plugin ecosystem. Optional paid sync exists but is never required; the files are yours either way.
- [Logseq](https://logseq.com/) `AGPL-3.0` 📄 — Outliner and daily journal on local Markdown/Org files, with backlinks and a graph view.
- [Joplin](https://joplinapp.org/) `AGPL-3.0` 🔁 — Notes and to-dos with end-to-end encrypted sync to targets you control (filesystem, WebDAV, your own server).
- [Zettlr](https://www.zettlr.com/) `GPL-3.0` 📄 — Markdown editor built for academic writing: Zettelkasten workflows, citations, exports.
- [Trilium Notes](https://github.com/TriliumNext/Trilium) `AGPL-3.0` 🗃️ — Hierarchical knowledge base in a local database, with scripting and optional self-hosted sync.
- [Anytype](https://anytype.io/) `Source-available` 🔁 — Local-first, end-to-end encrypted workspaces; identity is a keyphrase you hold, not an account.

## Tasks & Productivity

- [Taskwarrior](https://taskwarrior.org/) `MIT` 📄 — Command-line task manager storing tasks in local data files; scriptable and fast.
- [Super Productivity](https://super-productivity.com/) `MIT` 🔁 — To-dos, time tracking, and break reminders; local data with optional sync via WebDAV or file providers you choose.
- [Loop Habit Tracker](https://github.com/iSoron/uhabits) `GPL-3.0` 📵 — Android habit tracker with charts and reminders; fully offline.

## Finance

- [Actual Budget](https://actualbudget.org/) `MIT` 🗃️ — Envelope budgeting that runs entirely on your device; optional sync via a server you host. Local data, importable/exportable.
- [GnuCash](https://www.gnucash.org/) `GPL-2.0-or-later` 📵 — Veteran double-entry accounting for desktop; local files, no cloud anywhere.
- [Plain Text Accounting](https://plaintextaccounting.org/) ([ledger](https://ledger-cli.org/) `BSD-3-Clause`, [hledger](https://hledger.org/) `GPL-3.0`, [beancount](https://github.com/beancount/beancount) `GPL-2.0`) 📄 — Your books as plain-text journal files under version control. The maximal sovereignty position for financial data.

## Passwords & Secrets

- [KeePassXC](https://keepassxc.org/) `GPL-3.0` 🗃️ 📵 — Offline password manager on the open KDBX format; sync the vault file with whatever you already trust.
- [pass](https://www.passwordstore.org/) `GPL-2.0-or-later` 📄 — The Unix password store: GPG-encrypted files in a directory tree, git-friendly.

## Files, Sync & Backup

- [Syncthing](https://syncthing.net/) `MPL-2.0` 🔁 — Continuous peer-to-peer file sync between your own devices. No server, no account, no cloud.
- [LocalSend](https://localsend.org/) `MIT` 📵 — Cross-platform AirDrop alternative over your local network; no internet, no account.
- [restic](https://restic.net/) `BSD-2-Clause` — Encrypted, deduplicated backups to local disks or any storage you control; your keys, open repository format.
- [BorgBackup](https://www.borgbackup.org/) `BSD-3-Clause` — Deduplicating, encrypted, compression-friendly backup archives you own end to end.

## Maps & Navigation

- [Organic Maps](https://organicmaps.app/) `Apache-2.0` 📵 — Offline maps and turn-by-turn navigation from OpenStreetMap data; no account, no tracking, no ads.
- [CoMaps](https://www.comaps.app/) `Apache-2.0` 📵 — Community-governed fork of Organic Maps with the same offline-first, no-tracking stance.
- [OsmAnd](https://osmand.net/) `GPL-3.0` 📵 — Deeply detailed offline OpenStreetMap browser and navigator for mobile.

## Reading & Media

- [Calibre](https://calibre-ebook.com/) `GPL-3.0` — E-book library manager and converter; your library is a local folder you can walk away with.
- [KOReader](https://koreader.rocks/) `AGPL-3.0` 📵 — Document and e-book reader for e-ink devices, phones, and desktop.
- [NetNewsWire](https://netnewswire.com/) `MIT` — Free RSS reader for Mac and iOS; feeds live on your device, no account required.
- [Newsboat](https://newsboat.org/) `MIT` — RSS/Atom reader for the terminal; plain config, local cache.
- [VLC](https://www.videolan.org/vlc/) `GPL-2.0-or-later` 📵 — Plays essentially any media file, forever, with no strings attached.

## Drawing & Diagrams

- [Excalidraw](https://excalidraw.com/) `MIT` — Virtual whiteboard that works offline in the browser with no login; scenes save to local files. Collaboration is optional and end-to-end encrypted.
- [draw.io Desktop](https://github.com/jgraph/drawio-desktop) `Apache-2.0` 📵 — The diagrams.net editor as an offline desktop app working on local files.
- [Xournal++](https://xournalpp.github.io/) `GPL-2.0-or-later` 📵 — Handwritten notes, PDF annotation, and sketching with stylus support.

## Photos

- [digiKam](https://www.digikam.org/) `GPL-2.0-or-later` 📵 — Professional photo management over your local library: tagging, faces, search.
- [darktable](https://www.darktable.org/) `GPL-3.0` 📵 — Raw photo developing and cataloguing; a darkroom that runs on your machine.

## Learning

- [Anki](https://apps.ankiweb.net/) `AGPL-3.0` 🔁 — Spaced-repetition flashcards; decks are local, and the optional AnkiWeb sync is free, not required.

## Local AI

Models you run on your own hardware. No API key, no per-token bill, no transcript leaving your machine.

- [Jan](https://jan.ai/) `AGPL-3.0` — Desktop ChatGPT alternative running open-weight models locally; conversations stored on your device.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) `MIT` 📵 — The engine of the local-inference movement: run open-weight LLMs on ordinary CPUs and GPUs, from a single binary.
- [Ollama](https://ollama.com/) `MIT` — Pull and run open-weight models locally with one command; models are files on your disk in an open format.

## Messaging

- [Briar](https://briarproject.org/) `GPL-3.0` 🔁 — Peer-to-peer encrypted messaging over Tor, Wi-Fi, or Bluetooth; no server and no phone number.
- [Jami](https://jami.net/) `GPL-3.0` 🔁 — Distributed calls and messaging; your "account" is a keypair generated on your device.

## Documents & Office

- [LibreOffice](https://www.libreoffice.org/) `MPL-2.0` 📵 — The full office suite on open document formats. The original sovereign software.

## Suites & Stores

- [SAFE App Store](https://github.com/rudi193-cmd/safe-app-store) `Various` 📄 🗃️ — Local-first app suite where every app declares its permissions and data flows in a manifest before install. *Disclosure: maintained by this list's author.*

## Building Sovereign Software

Resources for building apps that pass the test, not just using them.

### Principles & essays

- [Local-first software: You own your data, in spite of the cloud](https://www.inkandswitch.com/local-first/) — the Ink & Switch essay that named the movement and set out its seven ideals.
- [File over app](https://stephango.com/file-over-app) — Steph Ango on why durable data formats outlive the software that writes them.
- [SQLite As An Application File Format](https://sqlite.org/appfileformat.html) — the case for a single, open, queryable file as your app's data store.
- [Plain Text Accounting](https://plaintextaccounting.org/) — a whole app category rebuilt on files; a masterclass in format-first design.

### Sync & data layer

- [Automerge](https://automerge.org/) — CRDT library for building collaborative local-first apps; JSON-shaped data that merges automatically.
- [Yjs](https://yjs.dev/) — high-performance CRDT framework powering many production collaborative editors.
- [crdt.tech](https://crdt.tech/) — the reference site for conflict-free replicated data types: papers, implementations, explainers.
- [ElectricSQL](https://electric-sql.com/) — Postgres-to-client sync engine for local-first apps.
- [CRDTs: The Hard Parts](https://martin.kleppmann.com/2020/07/06/crdt-hard-parts-hydra.html) — Martin Kleppmann's talk on where naive CRDT usage breaks down.

### Community

- [localfirstweb.dev](https://localfirstweb.dev/) — the Local-First Web community: meetups, newsletter, directory.
- [localfirst.fm](https://www.localfirst.fm/) — podcast interviewing the people building this space.
- [Local-First Conf](https://www.localfirstconf.com/) — the movement's annual conference.
- [selfh.st](https://selfh.st/) — weekly news and app directory for the self-hosted movement.
- [Self-Hosted podcast](https://selfhosted.show/) — long-running show on running your own services.

## Papers & Research

Academic grounding for the movement — local-first computing, digital sovereignty, and sovereign AI.

### Local-first & CRDTs

- [Local-first software: You own your data, in spite of the cloud](https://www.inkandswitch.com/local-first/) — Kleppmann, Wiggins, van Hardenberg & McGranaghan (Onward! 2019). The founding paper; the essay page includes the full text.
- [Conflict-free Replicated Data Types](https://inria.hal.science/inria-00609399) — Shapiro, Preguiça, Baquero & Zawirski (SSS 2011). The paper that formalized CRDTs.
- [A Conflict-Free Replicated JSON Datatype](https://arxiv.org/abs/1608.03960) — Kleppmann & Beresford (2017). CRDTs generalized to arbitrary JSON documents.

### Digital sovereignty & the self-hosted web

- [Digital sovereignty](https://policyreview.info/concepts/digital-sovereignty) — Pohle & Thiel (Internet Policy Review, 2020). The standard survey of what "sovereignty" means applied to computing.
- [Survey on Digital Sovereignty and Identity](https://dl.acm.org/doi/10.1145/3616400) — ACM Computing Surveys. Self-sovereign identity and data control, systematized.
- [Towards a decentralized data privacy protocol for self-sovereignty in the digital world](https://arxiv.org/abs/2404.12837) — a protocol design for user-held privacy preferences, self-hosted or delegated.
- [Solid Project](https://solidproject.org/) — Tim Berners-Lee's personal-data-store architecture: your data in a pod you control, apps come to you.

### Sovereign AI

- [Sovereign AI: Rethinking Autonomy in the Age of Global Interdependence](https://arxiv.org/abs/2511.15734) — what it takes to own the AI stack: data, models, compute, governance.
- [Trustless Autonomy: Understanding Motivations, Benefits, and Governance Dilemmas in Self-Sovereign Decentralized AI Agents](https://arxiv.org/abs/2505.09757) — the self-sovereign framing applied to autonomous agents.
- [My self-sovereign / local / private / secure LLM setup](https://vitalik.eth.limo/general/2026/04/02/secure_llms.html) — Vitalik Buterin's practical walkthrough of running capable AI with nothing leaving your machine.

## Related Lists

- [awesome-local-first (alexanderop)](https://github.com/alexanderop/awesome-local-first) — the developer side: sync engines, CRDTs, databases, talks.
- [awesome-local-first (schickling)](https://github.com/schickling/awesome-local-first) — local-first projects with a collaboration focus.
- [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) — apps you run on your own server. Complementary: sovereignty with a server in it.
- [awesome-no-login-web-apps](https://github.com/aviaryan/awesome-no-login-web-apps) — browser tools that work without an account.
- [awesome-privacy](https://github.com/pluja/awesome-privacy) — privacy-respecting alternatives to mainstream services.

## Contributing

Found an app that passes the [Sovereignty Test](#the-sovereignty-test)? See [CONTRIBUTING.md](CONTRIBUTING.md).
One app per pull request, with the checklist filled in.

## License

[CC0 1.0 Universal](LICENSE) — public domain. Take it, fork it, mirror it. That's the point.
