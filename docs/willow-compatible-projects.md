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
| [radio-active](https://github.com/deep5050/radio-active) | 587 | Internet radio player from the terminal, Shazam integration | manifest + permission | `network_read` |
| [ytm-player](https://github.com/peternaame-boop/ytm-player) | 410 | YouTube Music TUI — synced lyrics, vim keybindings, mpv backend | manifest + permission | `network_read` |
| [coding-with-beat](https://github.com/jaychempan/coding-with-beat) | 115 | Retro pixel DJ for the terminal — karaoke lyrics, panics when tests fail | manifest + shim | `local_llm`, `file_read` |

### Games

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [cli-chess](https://github.com/trevorbayless/cli-chess) | 295 | Chess vs Fairy-Stockfish engine locally, or online via Lichess | manifest-only | `file_read` (offline mode) |
| [smassh](https://github.com/kraanzu/smassh) | 2006 | Typing speed test TUI — MonkeyType-style, fully local | manifest-only | — |
| [usolitaire](https://github.com/eliasdorneles/usolitaire) | 103 | Solitaire in the terminal, Textual, unicode graphics | manifest-only | — |

### Creative

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [textual-paint](https://github.com/1j01/textual-paint) | 1110 | MS Paint recreated in the terminal — full ANSI/ASCII art editor | manifest-only | `file_read`, `file_write` |

### Science & Niche Hardware

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [SpliceCraft](https://github.com/Binomica-Labs/SpliceCraft) | 165 | Plasmid map viewer, sequence editor, and cloning workbench — pure Python, Textual TUI | manifest-only | `file_read`, `file_write` |
| [contact](https://github.com/pdxlocations/contact) | 336 | Meshtastic mesh radio chat — curses TUI over LoRa hardware | manifest + permission | `bluetooth` / serial |
| [FreeDATA](https://github.com/DJ2LS/FreeDATA) | 207 | Send files and chat messages over HF radio via Codec2 digital modes | manifest + permission | `bluetooth` / serial |
| [retro-adsb-radar](https://github.com/nicespoon/retro-adsb-radar) | 252 | Real-time aircraft radar with retro styling — reads local RTL-SDR or network ADS-B feed | manifest + permission | `network_read` |
| [HoldSpeak](https://github.com/karolswdev/HoldSpeak) | 277 | Local voice typing and meeting transcription via Whisper — Textual TUI | manifest-only | `local_llm`, `file_write` |
| [vocalinux](https://github.com/jatinkrmalik/vocalinux) | 389 | 100% offline voice dictation for Linux, GPU-accelerated, Whisper/VOSK | manifest-only | `local_llm` |

### OSINT & Signals

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [Shadowbroker](https://github.com/BigBodyCobain/Shadowbroker) | 9367 | Track private jets, spy satellites, seismic events in one interface — AI agent hookable | manifest + permission | `network_read` |

### Communication

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [tg](https://github.com/paul-nameless/tg) | 1168 | Telegram TUI client — curses-based, local credential storage | manifest + permission | `network_read` |
| [tewi](https://github.com/anlar/tewi) | 153 | BitTorrent TUI — controls Transmission, qBittorrent, or Deluge locally | manifest + permission | `network_read` |

---

## Useful & Low-Friction

### Developer Tools

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [posting](https://github.com/darrenburns/posting) | 12068 | Full API client TUI — like Postman but terminal-native, collections stored locally | manifest-only | `file_read`, `file_write` |
| [RecoverPy](https://github.com/PabloLec/RecoverPy) | 1771 | Interactively find and recover deleted/overwritten files in terminal | manifest-only | `file_read` |
| [toolong](https://github.com/Textualize/toolong) | 3922 | Log file viewer — tail, merge, search logs and JSONL, Textual | manifest-only | `file_read` |
| [isd](https://github.com/kainctl/isd) | 2118 | Interactive systemd TUI — browse, start, stop units with live logs | manifest-only | `file_read` |
| [cronboard](https://github.com/antoniorodr/cronboard) | 1399 | Terminal dashboard for managing cron jobs locally and on servers | manifest-only | `file_read`, `file_write` |
| [snip](https://github.com/phlx0/snip) | 103 | Code snippet manager — offline, SQLite, Textual, vim keybindings | manifest-only | `file_read`, `file_write` |
| [twig](https://github.com/workdone0/twig) | 163 | JSON/YAML viewer TUI — fast, interactive, privacy-first | manifest-only | `file_read` |
| [fast-resume](https://github.com/angristan/fast-resume) | 103 | Find and resume any coding agent session — Tantivy search, Textual | manifest-only | `file_read` |
| [kanban-tui](https://github.com/Zaloog/kanban-tui) | 253 | Kanban board TUI — already tagged `claude-skills`, designed for agent use | manifest-only | `file_read`, `file_write` |
| [taskdog](https://github.com/Kohei-Wada/taskdog) | 306 | Task manager with intelligent schedule optimization — has MCP support built in | manifest-only | `file_read`, `file_write` |

### Productivity & Personal

| Project | Stars | Description | Effort | Permissions |
|---------|-------|-------------|--------|-------------|
| [Bagels](https://github.com/EnhancedJax/Bagels) | 2813 | Expense tracker TUI — Textual, SQLite, fully local | manifest-only | `file_read`, `file_write` |
| [dooit](https://github.com/dooit-org/dooit) | 2900 | Todo manager TUI — Textual, extensible, local | manifest-only | `file_read`, `file_write` |
| [topydo](https://github.com/topydo/topydo) | 925 | Todo list CLI using todo.txt format — cross-platform, local files | manifest-only | `file_read`, `file_write` |
| [girok](https://github.com/noisrucer/girok) | 503 | Beautiful CLI scheduler/calendar — local SQLite | manifest-only | `file_read`, `file_write` |
| [frogmouth](https://github.com/Textualize/frogmouth) | 3211 | Markdown browser for the terminal — local file navigation | manifest-only | `file_read` |
| [browsr](https://github.com/juftin/browsr) | 591 | Pleasant file explorer TUI — local filesystems | manifest-only | `file_read` |
| [erys](https://github.com/natibek/erys) | 149 | Jupyter Notebook viewer TUI — browse and run notebooks in terminal | manifest-only | `file_read`, `file_write` |

---

## Notes

- **SpliceCraft** is the most unusual find — a molecular biology workbench that is architecturally identical to the store's tool pattern.
- **kanban-tui** and **taskdog** already have MCP or agent-skill awareness — lowest integration friction of anything here.
- **textual-paint** is pure fun and a good showcase app for the store TUI.
- **Shadowbroker** is the highest-leverage network app — pairs well with Willow KB writes for persistent tracking.
- Ham radio / mesh radio apps (**contact**, **FreeDATA**, **retro-adsb-radar**) represent a whole off-grid signals category the store doesn't have yet.
- This list will grow — search strategy: `topic:textual language:python`, `topic:local-first language:python`, `topic:tui language:python`, hobby-specific topics.
