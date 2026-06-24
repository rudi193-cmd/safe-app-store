# Willow-Compatible External Projects

External GitHub projects that could run under the SAFE App Store with minimal effort.

**Compatibility bar:** Python, local-first or low-dependency, CLI/TUI entry point, file/SQLite storage, no mandatory web server. Adding a `safe-app-manifest.json` and wiring a `make run` entry point is the only required change in most cases.

**Effort tiers:**
- `manifest-only` — add manifest + entry point, done
- `manifest + permission` — also declare a non-default permission (network_read, bluetooth, etc.)
- `manifest + shim` — thin CLI wrapper needed before manifest

---

## Fun & Unique

### Music & Audio

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [maestro-cli](https://github.com/PrajwalVandana/maestro-cli) | 231 | Local audio player (MP3/FLAC/WAV/OGG) with terminal visualizer | manifest-only | `file_read` |
| [pulsemixer](https://github.com/GeorgeFilipkin/pulsemixer) | 807 | CLI/curses mixer for PulseAudio — control system audio from terminal | manifest-only | — |
| [spotui](https://github.com/ceuk/spotui) | 572 | Spotify in the terminal — full playback control, search, playlists | manifest + permission | `network_read` |
| [radio-active](https://github.com/deep5050/radio-active) | 587 | Internet radio player from the terminal, Shazam integration | manifest + permission | `network_read` |
| [ytm-player](https://github.com/peternaame-boop/ytm-player) | 410 | YouTube Music TUI — synced lyrics, vim keybindings, mpv backend | manifest + permission | `network_read` |
| [castero](https://github.com/xgi/castero) | 686 | TUI podcast client — download, stream, manage feeds locally | manifest + permission | `network_read`, `file_write` |
| [coding-with-beat](https://github.com/jaychempan/coding-with-beat) | 115 | Retro pixel DJ for the terminal — karaoke lyrics, panics when tests fail | manifest + shim | `file_read` |
| [parllama](https://github.com/paulrobello/parllama) | 476 | TUI for Ollama — chat, manage models, local-first LLM interface | manifest-only | `local_llm` |

### Games & Recreation

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [cli-chess](https://github.com/trevorbayless/cli-chess) | 295 | Chess vs Fairy-Stockfish engine locally, or online via Lichess | manifest-only | `file_read` |
| [smassh](https://github.com/kraanzu/smassh) | 2006 | Typing speed test TUI — MonkeyType-style, fully local, highly customizable | manifest-only | — |
| [typr](https://github.com/Sakura-sx/typr) | 233 | TUI typing practice with adaptive word selection (keybr-inspired algorithm) | manifest-only | — |
| [usolitaire](https://github.com/eliasdorneles/usolitaire) | 103 | Solitaire in the terminal, Textual, unicode graphics | manifest-only | — |
| [mitype](https://github.com/Mithil467/mitype) | 437 | Typing speed test in the terminal — curses-based, minimal, smooth | manifest-only | — |

### Hobbies & Virtual Companions

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [botany](https://github.com/jifunks/botany) | 532 | Command-line virtual plant buddy — grows over time, curses, pure local fun | manifest-only | `file_read`, `file_write` |
| [trackma](https://github.com/z411/trackma) | 880 | Anime and manga list tracker — curses TUI, multi-site (MAL, AniList, Kitsu), local cache | manifest + permission | `network_read`, `file_write` |
| [polyterm](https://github.com/NYTEMODEONLY/polyterm) | 318 | Prediction markets (Polymarket) in the terminal — live odds, TUI | manifest + permission | `network_read` |

### Creative & Art

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [textual-paint](https://github.com/1j01/textual-paint) | 1110 | MS Paint recreated in the terminal — full ANSI/ASCII art editor | manifest-only | `file_read`, `file_write` |
| [durdraw](https://github.com/cmang/durdraw) | 1748 | ASCII/ANSI art editor with animation, 256 colors, CP437, Unicode — like a demoscene tool | manifest-only | `file_read`, `file_write` |
| [uniplot](https://github.com/olavolav/uniplot) | 455 | Terminal data plotting with Unicode/Braille at 4x resolution — no GUI needed | manifest + shim | `file_read` |

### Science, Space & Niche Hardware

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [termtrack](https://github.com/trehn/termtrack) | 544 | Track satellites in real-time in your terminal — renders a world map with orbits | manifest-only | `network_read` (TLE fetch) |
| [SpliceCraft](https://github.com/Binomica-Labs/SpliceCraft) | 165 | Plasmid map viewer, sequence editor, and cloning workbench — pure Python, Textual TUI | manifest-only | `file_read`, `file_write` |
| [contact](https://github.com/pdxlocations/contact) | 336 | Meshtastic mesh radio chat — curses TUI over LoRa hardware | manifest + permission | `bluetooth` / serial |
| [FreeDATA](https://github.com/DJ2LS/FreeDATA) | 207 | Send files and chat messages over HF radio via Codec2 digital modes | manifest + permission | `bluetooth` / serial |
| [retro-adsb-radar](https://github.com/nicespoon/retro-adsb-radar) | 252 | Real-time aircraft radar with retro styling — reads local RTL-SDR or network ADS-B feed | manifest + permission | `network_read` |
| [HoldSpeak](https://github.com/karolswdev/HoldSpeak) | 277 | Local voice typing and meeting transcription via Whisper — Textual TUI | manifest-only | `local_llm`, `file_write` |
| [vocalinux](https://github.com/jatinkrmalik/vocalinux) | 389 | 100% offline voice dictation for Linux, GPU-accelerated, Whisper/VOSK | manifest-only | `local_llm` |
| [rtui](https://github.com/eduidl/rtui) | 209 | TUI for ROS (Robot Operating System) — inspect topics, services, nodes live | manifest-only | — |

### OSINT & Signals

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [Shadowbroker](https://github.com/BigBodyCobain/Shadowbroker) | 9367 | Track private jets, spy satellites, seismic events in one interface — AI agent hookable | manifest + permission | `network_read` |
| [NetOrbit](https://github.com/ZXCurban/NetOrbit) | 242 | Network traffic visualization with live GeoIP — ASCII art, terminal graphics | manifest-only | `network_read` |

### Communication & Social

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [tg](https://github.com/paul-nameless/tg) | 1168 | Telegram TUI client — curses-based, local credential storage | manifest + permission | `network_read` |
| [endcord](https://github.com/sparklost/endcord) | 862 | Feature-rich Discord TUI client — active project, Rich Presence support | manifest + permission | `network_read` |
| [tewi](https://github.com/anlar/tewi) | 153 | BitTorrent TUI — controls Transmission, qBittorrent, or Deluge locally | manifest + permission | `network_read` |

### Reading & Media

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [baca](https://github.com/wustho/baca) | 513 | TUI ebook reader — epub and mobi, fully local, keyboard-driven | manifest-only | `file_read` |
| [euporie](https://github.com/joouha/euporie) | 2587 | Jupyter notebooks in the terminal — full execution, Sixel graphics, vim bindings | manifest-only | `file_read`, `file_write` |
| [TermFeed](https://github.com/iamaziz/TermFeed) | 261 | Simple terminal RSS reader — local feed cache, minimal | manifest + permission | `network_read`, `file_write` |
| [feeds.fun](https://github.com/Tiendil/feeds.fun) | 371 | RSS reader with LLM tagging and scoring — self-hosted, SQLite | manifest + permission | `network_read`, `local_llm` |

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
| [twig](https://github.com/workdone0/twig) | 163 | JSON/YAML viewer TUI — fast, interactive, privacy-first | manifest-only | `file_read` |
| [fast-resume](https://github.com/angristan/fast-resume) | 103 | Find and resume any coding agent session — Tantivy search, Textual | manifest-only | `file_read` |
| [kanban-tui](https://github.com/Zaloog/kanban-tui) | 253 | Kanban board TUI — already tagged `claude-skills`, designed for agent use | manifest-only | `file_read`, `file_write` |
| [taskdog](https://github.com/Kohei-Wada/taskdog) | 306 | Task manager with schedule optimization — has MCP support built in | manifest-only | `file_read`, `file_write` |
| [sqlit](https://github.com/Maxteabag/sqlit) | 4391 | SQL database browser TUI — SQLite, MySQL, PostgreSQL; explore and query locally | manifest-only | `file_read`, `file_write` |
| [rexi](https://github.com/royreznik/rexi) | 393 | Regex testing TUI — live preview, Textual, no network | manifest-only | — |
| [calcpy](https://github.com/idanpa/calcpy) | 117 | Terminal calculator with Python and SymPy math — symbolic algebra in the REPL | manifest-only | — |
| [nvitop](https://github.com/XuehaiPan/nvitop) | 6974 | NVIDIA GPU process monitor TUI — essential companion for local_llm apps | manifest-only | — |
| [pingtop](https://github.com/laixintao/pingtop) | 537 | Ping multiple servers simultaneously — top-like live TUI, pure Python | manifest-only | `network_read` |
| [px](https://github.com/walles/px) | 324 | ps/top/pstree for humans — process tree TUI, no root required | manifest-only | — |
| [ClockTemp](https://github.com/arthur-dnts/ClockTemp) | 104 | TUI clock showing time, date, and local temperature — charming ambient display | manifest + permission | `network_read` |

### Productivity & Personal

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [calcure](https://github.com/anufrievroman/calcure) | 2301 | Modern TUI calendar and task manager — customizable, local ICS/todo files | manifest-only | `file_read`, `file_write` |
| [Bagels](https://github.com/EnhancedJax/Bagels) | 2813 | Expense tracker TUI — Textual, SQLite, fully local | manifest-only | `file_read`, `file_write` |
| [dooit](https://github.com/dooit-org/dooit) | 2901 | Todo manager TUI — Textual, extensible with plugins, local | manifest-only | `file_read`, `file_write` |
| [topydo](https://github.com/topydo/topydo) | 925 | Todo list CLI using todo.txt format — cross-platform, local files | manifest-only | `file_read`, `file_write` |
| [girok](https://github.com/noisrucer/girok) | 503 | Beautiful CLI scheduler/calendar — local SQLite | manifest-only | `file_read`, `file_write` |
| [frogmouth](https://github.com/Textualize/frogmouth) | 3211 | Markdown browser for the terminal — local file navigation | manifest-only | `file_read` |
| [browsr](https://github.com/juftin/browsr) | 591 | Pleasant file explorer TUI — local filesystems | manifest-only | `file_read` |
| [rovr](https://github.com/NSPC911/rovr) | 382 | Stylish, batteries-included terminal file manager | manifest-only | `file_read`, `file_write` |
| [erys](https://github.com/natibek/erys) | 149 | Jupyter Notebook viewer TUI — browse and run notebooks in terminal | manifest-only | `file_read`, `file_write` |
| [baca](https://github.com/wustho/baca) | 513 | TUI ebook reader — epub and mobi, fully local, keyboard-driven | manifest-only | `file_read` |

---

## Notes

- **visidata** (9k stars) is arguably the most powerful single tool on this list — opens almost any data format in a spreadsheet TUI. A natural companion to law-gazelle and private-ledger.
- **durdraw** is the deeper version of textual-paint — animation support, CP437, proper demoscene-style editing.
- **calcure** fills the calendar gap the store doesn't have.
- **euporie** lets you run Jupyter notebooks entirely in the terminal — useful for nasa-archive and data-heavy apps.
- **SpliceCraft** is the most unusual find — a molecular biology workbench architecturally identical to the store's tool pattern.
- **kanban-tui** and **taskdog** already have MCP/agent-skill awareness — lowest integration friction of anything here.
- Ham radio / mesh / ADS-B apps (**contact**, **FreeDATA**, **retro-adsb-radar**, **termtrack**) form a coherent off-grid signals category the store doesn't have yet.
- **Shadowbroker** pairs naturally with Willow KB writes for persistent tracking over time.
- **nvitop** (7k stars) is a must-have companion for any `local_llm` app — shows GPU memory pressure live.
- **sqlit** (4k stars) pairs naturally with any store app that uses SQLite — law-gazelle, private-ledger, Bagels, dooit.
- **botany** is the most charming low-stakes local app: a virtual plant that grows in real time. Zero permissions, maximum delight.
- **trackma** is the only anime/manga tracker on the list — curses TUI, multi-site, surprisingly polished.
- Search vectors that keep producing results: `topic:textual language:python`, `topic:tui language:python` (pages 1-6+), `topic:curses language:python`, hobby topics (`topic:ham-radio`, `topic:astronomy`, `topic:podcast`, `topic:anime`).
