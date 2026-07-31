# Willow-Compatible External Projects

> **Status:** Scout list — research backlog, **not** the authoritative catalog (see
> `.willow/store/` and `catalog.json`). Add entries to the real catalog with
> `status: seeded` only after a manifest exists and `make run app=<name>`
> works (`status` is the P1 state enum — seeded/building/gated/stalled/
> archived — since `docs/store_refit_plan.md`'s status-vocabulary migration;
> it no longer accepts `coming_soon`).
>
> **Stars:** GitHub counts as of 2026-06 (third pass). Refresh before marketing copy.
>
> **See also:** [app_store_vision_and_gaps.md](app_store_vision_and_gaps.md) ·
> [app_registry_spec.md](specs/app_registry_spec.md) · permission labels in `tui.py` ·
> Grove borrow map ([grove-starter-borrow-map.md](../../safe-app-willow-grove/docs/synthesis/grove-starter-borrow-map.md))
>
> **~61 entries** in tables (4 deduped — see [Overlaps](#overlaps)). **Starter pack:** 10
> promote-first targets in [Starter pack](#starter-pack-promote-first). Across 15 categories
> (Fun & Unique · Useful & Low-Friction).

External GitHub projects that could run under the SAFE App Store with minimal effort.

**Compatibility bar:** Python, local-first or low-dependency, CLI/TUI entry point, file/SQLite
storage, no mandatory web server. Most need only `safe-app-manifest.json`, an `entry_point`, and a
`make run` target (standalone repo via `app_install`, or `apps/<name>/` in the monorepo).

**Integration effort** (code work — separate from the Permissions column):

| Tier | Meaning |
|------|---------|
| `manifest-only` | Upstream CLI/TUI runs as-is; add manifest + `make run` |
| `manifest + shim` | Thin wrapper (argv, env, or path normalization) before manifest |

**Permissions column:** strings to declare in `safe-app-manifest.json` (see `_PERM_LABEL` in
`tui.py`). `—` = no gated permissions beyond ordinary local file access. Permission choice is
independent of integration tier — a `manifest-only` app may still need `network_read` or
`local_llm`.

---

## Fun & Unique

### Music & Audio

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [maestro-cli](https://github.com/PrajwalVandana/maestro-cli) | 231 | Local audio player (MP3/FLAC/WAV/OGG) with terminal visualizer | manifest-only | `file_read` |
| [pulsemixer](https://github.com/GeorgeFilipkin/pulsemixer) | 807 | CLI/curses mixer for PulseAudio — control system audio from terminal | manifest-only | — |
| [spotui](https://github.com/ceuk/spotui) | 572 | Spotify in the terminal — full playback control, search, playlists | manifest-only | `network_read` |
| [radio-active](https://github.com/deep5050/radio-active) | 587 | Internet radio player from the terminal, Shazam integration | manifest-only | `network_read` |
| [ytm-player](https://github.com/peternaame-boop/ytm-player) | 410 | YouTube Music TUI — synced lyrics, vim keybindings, mpv backend | manifest-only | `network_read` |
| [castero](https://github.com/xgi/castero) | 686 | TUI podcast client — download, stream, manage feeds locally | manifest-only | `network_read`, `file_write` |
| [coding-with-beat](https://github.com/jaychempan/coding-with-beat) | 115 | Retro pixel DJ for the terminal — karaoke lyrics, panics when tests fail | manifest + shim | `file_read` |
| [parllama](https://github.com/paulrobello/parllama) | 476 | TUI for Ollama — chat, manage models, local-first LLM interface | manifest-only | `local_llm` |

### Games & Recreation

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [cli-chess](https://github.com/trevorbayless/cli-chess) | 295 | Chess vs Fairy-Stockfish engine locally, or online via Lichess | manifest-only | `file_read`, `network_read` (Lichess) |
| [smassh](https://github.com/kraanzu/smassh) | 2006 | Typing speed test TUI — MonkeyType-style, fully local, highly customizable | manifest-only | — |
| [typr](https://github.com/Sakura-sx/typr) | 233 | TUI typing **practice** with adaptive word selection (keybr-inspired) — not a speed test | manifest-only | — |
| [usolitaire](https://github.com/eliasdorneles/usolitaire) | 103 | Solitaire in the terminal, Textual, unicode graphics | manifest-only | — |

*Typing **speed test** alternate **mitype** (437★, minimal curses) deduped — prefer **smassh**; see [Overlaps](#overlaps).*

### Hobbies & Virtual Companions

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [botany](https://github.com/jifunks/botany) | 532 | Command-line virtual plant buddy — grows over time, curses, pure local fun | manifest-only | `file_read`, `file_write` |
| [trackma](https://github.com/z411/trackma) | 880 | Anime and manga list tracker — curses TUI, multi-site (MAL, AniList, Kitsu), local cache | manifest-only | `network_read`, `file_write` |
| [polyterm](https://github.com/NYTEMODEONLY/polyterm) | 318 | Prediction markets (Polymarket) in the terminal — live odds, TUI | manifest-only | `network_read` |

### Creative & Art

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [textual-paint](https://github.com/1j01/textual-paint) | 1110 | MS Paint recreated in the terminal — full ANSI/ASCII art editor | manifest-only | `file_read`, `file_write` |
| [durdraw](https://github.com/cmang/durdraw) | 1748 | ASCII/ANSI art editor with animation, 256 colors, CP437, Unicode — demoscene-style | manifest-only | `file_read`, `file_write` |
| [uniplot](https://github.com/olavolav/uniplot) | 455 | Terminal data plotting with Unicode/Braille at 4x resolution — no GUI needed | manifest + shim | `file_read` |

*For terminal art, **durdraw** supersedes **textual-paint** on features — keep both in scout; promote **durdraw** first ([Overlaps](#overlaps)).*

### Science, Space & Niche Hardware

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [termtrack](https://github.com/trehn/termtrack) | 544 | Track satellites in real-time in your terminal — renders a world map with orbits | manifest-only | `network_read` |
| [SpliceCraft](https://github.com/Binomica-Labs/SpliceCraft) | 165 | Plasmid map viewer, sequence editor, and cloning workbench — pure Python, Textual TUI | manifest-only | `file_read`, `file_write` |
| [contact](https://github.com/pdxlocations/contact) | 336 | Meshtastic mesh radio chat — curses TUI over LoRa hardware | manifest-only | `bluetooth` |
| [FreeDATA](https://github.com/DJ2LS/FreeDATA) | 207 | Send files and chat messages over HF radio via Codec2 digital modes | manifest-only | `bluetooth` |
| [retro-adsb-radar](https://github.com/nicespoon/retro-adsb-radar) | 252 | Real-time aircraft radar with retro styling — reads local RTL-SDR or network ADS-B feed | manifest-only | `network_read` |
| [HoldSpeak](https://github.com/karolswdev/HoldSpeak) | 277 | Local voice typing and **meeting transcription** via Whisper — Textual TUI | manifest-only | `local_llm`, `file_write` |
| [vocalinux](https://github.com/jatinkrmalik/vocalinux) | 389 | 100% offline **dictation** for Linux, GPU-accelerated, Whisper/VOSK | manifest-only | `local_llm` |
| [rtui](https://github.com/eduidl/rtui) | 209 | TUI for ROS (Robot Operating System) — inspect topics, services, nodes live | manifest-only | — |

### OSINT & Signals

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [Shadowbroker](https://github.com/BigBodyCobain/Shadowbroker) | 9367 | Track private jets, spy satellites, seismic events in one interface — AI agent hookable | manifest-only | `network_read` |
| [NetOrbit](https://github.com/ZXCurban/NetOrbit) | 242 | Network traffic visualization with live GeoIP — ASCII art, terminal graphics | manifest-only | `network_read` |

*Satellite-only **termtrack** overlaps Shadowbroker's orbit slice — promote **termtrack** for lightweight TLE maps, **Shadowbroker** for multi-source OSINT ([Overlaps](#overlaps)).*

### Communication & Social

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [tg](https://github.com/paul-nameless/tg) | 1168 | Telegram TUI client — curses-based, local credential storage | manifest-only | `network_read` |
| [endcord](https://github.com/sparklost/endcord) | 862 | Feature-rich Discord TUI client — active project, Rich Presence support | manifest-only | `network_read` |
| [tewi](https://github.com/anlar/tewi) | 153 | BitTorrent TUI — controls Transmission, qBittorrent, or Deluge locally | manifest-only | `network_read` |

### Reading & Media

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [baca](https://github.com/wustho/baca) | 513 | TUI ebook reader — epub and mobi, fully local, keyboard-driven | manifest-only | `file_read` |
| [euporie](https://github.com/joouha/euporie) | 2587 | Jupyter notebooks in the terminal — full execution, Sixel graphics, vim bindings | manifest-only | `file_read`, `file_write` |
| [feeds.fun](https://github.com/Tiendil/feeds.fun) | 371 | RSS reader with LLM tagging and scoring — self-hosted, SQLite | manifest-only | `network_read`, `local_llm` |

*Jupyter viewer **erys** (149★) deduped — **euporie** runs notebooks; RSS alternate **TermFeed** (261★) deduped — prefer **feeds.fun** for `local_llm`. See [Overlaps](#overlaps).*

---

## Useful & Low-Friction

### Developer Tools

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [posting](https://github.com/darrenburns/posting) | 12068 | Full API client TUI — like Postman but terminal-native, collections stored locally | manifest-only | `file_read`, `file_write` |
| [visidata](https://github.com/saulpw/visidata) | 9146 | Terminal spreadsheet multitool — open CSV, JSON, SQLite, HDF5, and more | manifest-only | `file_read`, `file_write` |
| [RecoverPy](https://github.com/PabloLec/RecoverPy) | 1771 | Interactively find and recover deleted/overwritten files in terminal | manifest-only | `file_read` |
| [toolong](https://github.com/Textualize/toolong) | 3922 | Log file viewer — tail, merge, search logs and JSONL, Textual | manifest-only | `file_read` |
| [austin-tui](https://github.com/P403n1x87/austin-tui) | 663 | Real-time Python profiler TUI — flame graph in terminal | manifest-only | — |
| [isd](https://github.com/kainctl/isd) | 2118 | Interactive systemd TUI — browse, start, stop units with live logs | manifest-only | — |
| [s-tui](https://github.com/amanusk/s-tui) | 5034 | CPU stress test and monitoring TUI — temperature, frequency, power, utilization | manifest-only | — |
| [cronboard](https://github.com/antoniorodr/cronboard) | 1399 | Terminal dashboard for managing cron jobs locally and on servers | manifest-only | `file_read`, `file_write` |
| [snip](https://github.com/phlx0/snip) | 103 | Code snippet manager — offline, SQLite, Textual, vim keybindings | manifest-only | `file_read`, `file_write` |
| [twig](https://github.com/workdone0/twig) | 163 | JSON/YAML **viewer** TUI — subset of what **visidata** opens | manifest-only | `file_read` |
| [fast-resume](https://github.com/angristan/fast-resume) | 103 | Find and resume any coding agent session — Tantivy search, Textual | manifest-only | `file_read` |
| [kanban-tui](https://github.com/Zaloog/kanban-tui) | 253 | Kanban board TUI — `claude-skills` tag, visual agent workflow | manifest-only | `file_read`, `file_write` |
| [taskdog](https://github.com/Kohei-Wada/taskdog) | 306 | Task manager with schedule optimization — **MCP** built in | manifest-only | `file_read`, `file_write` |
| [sqlit](https://github.com/Maxteabag/sqlit) | 4391 | SQL database browser TUI — SQLite, MySQL, PostgreSQL; explore and query locally | manifest-only | `file_read`, `file_write` |
| [rexi](https://github.com/royreznik/rexi) | 393 | Regex testing TUI — live preview, Textual, no network | manifest-only | — |
| [calcpy](https://github.com/idanpa/calcpy) | 117 | Terminal calculator with Python and SymPy math — symbolic algebra in the REPL | manifest-only | — |
| [nvitop](https://github.com/XuehaiPan/nvitop) | 6974 | NVIDIA GPU process monitor TUI — essential companion for local_llm apps | manifest-only | — |
| [pingtop](https://github.com/laixintao/pingtop) | 537 | Ping multiple servers simultaneously — top-like live TUI, pure Python | manifest-only | `network_read` |
| [px](https://github.com/walles/px) | 324 | ps/top/pstree for humans — process tree TUI, no root required | manifest-only | — |
| [ClockTemp](https://github.com/arthur-dnts/ClockTemp) | 104 | TUI clock showing time, date, and local temperature — charming ambient display | manifest-only | `network_read` |

### Productivity & Personal

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [calcure](https://github.com/anufrievroman/calcure) | 2301 | Modern TUI calendar **and** task manager — local ICS/todo files | manifest-only | `file_read`, `file_write` |
| [Bagels](https://github.com/EnhancedJax/Bagels) | 2813 | Expense tracker TUI — Textual, SQLite, fully local | manifest-only | `file_read`, `file_write` |
| [dooit](https://github.com/dooit-org/dooit) | 2901 | Todo manager TUI — Textual, extensible with plugins, local | manifest-only | `file_read`, `file_write` |
| [topydo](https://github.com/topydo/topydo) | 925 | Todo list CLI — **todo.txt** format purists | manifest-only | `file_read`, `file_write` |
| [frogmouth](https://github.com/Textualize/frogmouth) | 3211 | Markdown browser for the terminal — local file navigation | manifest-only | `file_read` |
| [browsr](https://github.com/juftin/browsr) | 591 | Pleasant file explorer TUI — read-focused | manifest-only | `file_read` |
| [rovr](https://github.com/NSPC911/rovr) | 382 | Terminal file manager — read/write, batteries included | manifest-only | `file_read`, `file_write` |

*Calendar alternate **girok** (503★) deduped — **calcure** fills the store calendar gap. See [Overlaps](#overlaps).*

---

## Overlaps

Multiple scouts often cover one catalog slot. **Pick first** = recommended promote target; alternates stay in scout until explicitly dropped.

| Slot | In scout | Pick first | Why |
|------|----------|------------|-----|
| Typing speed test | smassh, ~~mitype~~ | **smassh** | Higher stars, MonkeyType-style, customizable |
| Typing practice | typr | **typr** | Different job than speed tests — adaptive drills |
| Terminal ASCII/ANSI art | textual-paint, durdraw | **durdraw** | Animation, CP437, demoscene depth |
| Terminal plotting | uniplot, visidata | **uniplot** for quick plots; **visidata** for tabular data | Different input shapes |
| Calendar + tasks | calcure, ~~girok~~, dooit (tasks only) | **calcure** | Fills store calendar gap; ICS/todo |
| Todo lists | dooit, topydo, calcure | **dooit** | Plugins, Textual; **topydo** if todo.txt required |
| Agent task boards | kanban-tui, taskdog | **taskdog** for MCP; **kanban-tui** for visual kanban + skills | Complementary — not mutually exclusive |
| File browse | browsr, rovr, frogmouth | **rovr** general FM; **frogmouth** markdown-only | browsr is read-only middle ground |
| Jupyter in terminal | euporie, ~~erys~~ | **euporie** | Full execution + Sixel; erys was viewer-only |
| RSS | feeds.fun, ~~TermFeed~~ | **feeds.fun** | SQLite + `local_llm` tagging fits fleet thesis |
| Ebook reader | baca | **baca** | Only entry — listed once under Reading & Media |
| Voice → text | HoldSpeak, vocalinux | **vocalinux** dictation; **HoldSpeak** meetings | Same Whisper stack, different UX |
| Satellites / OSINT | termtrack, Shadowbroker | **termtrack** lightweight; **Shadowbroker** multi-source | Shadowbroker subsumes orbit tracking |
| Network viz | NetOrbit, pingtop | **NetOrbit** GeoIP traffic; **pingtop** latency | Adjacent, not duplicate |
| SQL vs spreadsheets | sqlit, visidata, twig | **sqlit** DB browser; **visidata** any table; **twig** JSON-only | Layered — often install together |
| Streaming audio | spotui, ytm-player, radio-active, castero, maestro-cli | **maestro-cli** local files; pick one streamer by service | No single winner |
| Ollama TUI | parllama | **parllama** | Only entry; pairs with **nvitop** |
| Process / system | px, s-tui, isd, austin-tui, nvitop | Each distinct scope | px processes; s-tui CPU thermals; isd systemd; nvitop GPU |

**Deduped from tables** (still valid GitHub projects — linked here for audit):

| Removed row | Kept as | Repo |
|-------------|---------|------|
| mitype | smassh | [Mithil467/mitype](https://github.com/Mithil467/mitype) |
| girok | calcure | [noisrucer/girok](https://github.com/noisrucer/girok) |
| erys | euporie | [natibek/erys](https://github.com/natibek/erys) |
| TermFeed | feeds.fun | [iamaziz/TermFeed](https://github.com/iamaziz/TermFeed) |

---

## Starter pack (promote first)

Ten projects from [Overlaps](#overlaps) picks — ordered for **manifest-only** onboarding that
closes real store gaps (calendar, data tooling, GPU/`local_llm` ops, agent workflows) without
diluting the sovereign-first thesis. All run standalone; none require Willow at runtime.

| Wave | App | `app_id` | Effort | Permissions | Why now | Pairs with |
|------|-----|----------|--------|-------------|---------|------------|
| 1 | [nvitop](https://github.com/XuehaiPan/nvitop) | `nvitop` | manifest-only | — | T500 + Ollama fleet needs live VRAM/process visibility before more `local_llm` apps ship | ask-jeles, parllama, feeds.fun, HoldSpeak |
| 1 | [parllama](https://github.com/paulrobello/parllama) | `parllama` | manifest-only | `local_llm` | Local Ollama chat/model UI — obvious companion to the inference stack already on host | nvitop, ask-jeles |
| 2 | [visidata](https://github.com/saulpw/visidata) | `visidata` | manifest-only | `file_read`, `file_write` | Opens CSV/JSON/SQLite/HDF5 in one TUI — flagship data apps export messy shapes | law-gazelle, private-ledger, nasa-archive |
| 2 | [sqlit](https://github.com/Maxteabag/sqlit) | `sqlit` | manifest-only | `file_read`, `file_write` | Browse/query SQLite files the suite already creates | law-gazelle, private-ledger, Bagels, dooit |
| 3 | [calcure](https://github.com/anufrievroman/calcure) | `calcure` | manifest-only | `file_read`, `file_write` | **Only calendar** on the scout list; explicit gap in current catalog | dooit, topydo |
| 3 | [taskdog](https://github.com/Kohei-Wada/taskdog) | `taskdog` | manifest-only | `file_read`, `file_write` | Built-in **MCP** — lowest friction for agent + human task loops | kanban-tui, ratatosk |
| 4 | [feeds.fun](https://github.com/Tiendil/feeds.fun) | `feeds-fun` | manifest-only | `network_read`, `local_llm` | Self-hosted RSS + local LLM tagging — sovereign news intake vs cloud readers | ask-jeles, the-binder |
| 4 | [kanban-tui](https://github.com/Zaloog/kanban-tui) | `kanban-tui` | manifest-only | `file_read`, `file_write` | Visual board + `claude-skills` tag; complements taskdog's MCP backend | taskdog |
| 5 | [toolong](https://github.com/Textualize/toolong) | `toolong` | manifest-only | `file_read` | JSONL/log tail for Nest pipeline, Kart output, and field-notes debugging | nest-seed, field-notes |
| 5 | [botany](https://github.com/jifunks/botany) | `botany` | manifest-only | `file_read`, `file_write` | Showcase app: local-only, delightful, proves the store isn't all spreadsheets | — |

**Waves 1–2** = infrastructure + data layer (do these before promoting more `local_llm` scouts).
**Waves 3–4** = productivity + fleet-aligned intake. **Wave 5** = ops polish + catalog charm.

**Grove overlap:** Several waves already have partial implementations in
[Willow Grove](https://github.com/rudi193-cmd/safe-app-willow-grove) (desk, Kart queue, vitals, KB).
Before promoting, read **[grove-starter-borrow-map.md](../../safe-app-willow-grove/docs/synthesis/grove-starter-borrow-map.md)**
(GSBRW) — *steal patterns into Grove panes* vs *wrap as standalone SAFE apps*.

**Deferred (wave 6+)** — strong scouts, higher permission or shim cost; pick after starter pack ships:

| App | Blocker / note |
|-----|----------------|
| [Shadowbroker](https://github.com/BigBodyCobain/Shadowbroker) | `network_read`; optional Willow KB write path needs design |
| [durdraw](https://github.com/cmang/durdraw) | Fun category; no suite gap — good second-wave delight |
| [euporie](https://github.com/joouha/euporie) | Notebook execution + Sixel; heavier deps than manifest-only suggests |
| [posting](https://github.com/darrenburns/posting) | API client; useful but not sovereign-core |
| contact / FreeDATA / retro-adsb-radar | `bluetooth` / hardware — after bt-controller patterns settle |

### Per-app promote checklist

1. Clone or `app_install` → `apps/<app_id>/` (or standalone SAFE repo; `app_id` = directory name).
2. `safe-app-manifest.json` + `entry_point` + `make run app=<app_id>`.
3. Smoke on host (T500): cold start, quit clean, permissions match manifest.
4. Add a keeping record at `stores/<major>/stored/<app_id>.json` (`docs/store_refit_plan.md` P1), then add the entry to `.willow/store/catalog.json` with `status: seeded` (or `building`/`gated`/`stalled` if it's already past that bar — `status` is generated from the keeping record's `state` and `catalog_lint.py --strict` will reject a mismatch; it no longer accepts `coming_soon`/`stable`).
5. Run `python tools/catalog_lint.py --strict` before pushing.
6. Mark row promoted in this doc (date + catalog `app_id` in [Overlaps](#overlaps) audit or a `promoted:` footnote).

---

## Notes

### Store fit

- **visidata** (9k stars) is arguably the most powerful single tool on this list — opens almost any data format in a spreadsheet TUI. A natural companion to law-gazelle and private-ledger.
- **calcure** fills the calendar gap the store doesn't have (see [Overlaps](#overlaps) vs girok).
- **euporie** lets you run Jupyter notebooks entirely in the terminal — useful for nasa-archive and data-heavy apps.
- **SpliceCraft** is the most unusual find — a molecular biology workbench architecturally identical to the store's tool pattern.
- **kanban-tui** and **taskdog** already have MCP/agent-skill awareness — lowest integration friction of anything here.
- Ham radio / mesh / ADS-B apps (**contact**, **FreeDATA**, **retro-adsb-radar**, **termtrack**) form a coherent off-grid signals category the store doesn't have yet.
- **Shadowbroker** pairs naturally with Willow KB writes for persistent tracking over time.
- **nvitop** (7k stars) is a must-have companion for any `local_llm` app — shows GPU memory pressure live.
- **sqlit** (4k stars) pairs naturally with any store app that uses SQLite — law-gazelle, private-ledger, Bagels, dooit.
- **botany** is the most charming low-stakes local app: a virtual plant that grows in real time. Local-only (`file_read`, `file_write`), maximum delight.
- **trackma** is the only anime/manga tracker on the list — curses TUI, multi-site, surprisingly polished.

### Discovery (repeatable)

- Search vectors that keep producing results: `topic:textual language:python`, `topic:tui language:python` (pages 1-6+), `topic:curses language:python`, hobby topics (`topic:ham-radio`, `topic:astronomy`, `topic:podcast`, `topic:anime`).

### Hygiene when promoting to catalog

1. Verify `entry_point` and deps on target hardware (GPU apps: pair with **nvitop**).
2. Add `safe-app-manifest.json` with `data_streams` + honest `permissions`.
3. Register in `.willow/store/` — do not add to `catalog.json` alone.
4. Archive scout row or mark promoted in a follow-up edit to this doc.
