from responder.formatter import result_block
from responder.state import AppState, Mode
import db.persons as persons_db
import db.fragments as fragments_db
import db.sources as sources_db


def cmd_mode(state: AppState, args: list) -> str:
    if not args:
        return result_block("Mode", f"Current mode: `{state.mode.value}`\nOptions: journal, listening, chat")
    m = args[0].lower()
    mapping = {"journal": Mode.JOURNAL, "listening": Mode.LISTENING, "chat": Mode.CHAT}
    if m not in mapping:
        return result_block("Mode", f"Unknown mode `{m}`. Use: journal, listening, chat")
    state.mode = mapping[m]
    msgs = {
        "journal": "Mode → `journal` — LLM offline. Commands only.",
        "listening": "Mode → `listening` — Jeles is listening.",
        "chat": "Mode → `chat` — Jeles is ready. Ask anything.",
    }
    return result_block("Mode", msgs[m])


def cmd_skin(state: AppState, args: list) -> str:
    if not args:
        return result_block("Skin", f"Current skin: `{state.skin}`\nOptions: mcm, 80s, 00s, 20s")
    skin = args[0].lower()
    if skin not in ("mcm", "80s", "00s", "20s"):
        return result_block("Skin", f"Unknown skin `{skin}`. Options: mcm, 80s, 00s, 20s")
    state.skin = skin
    state.save_config()
    return result_block("Skin", f"Skin → `{skin}` — reload the page to apply.")


def cmd_status(conn, state: AppState) -> str:
    try:
        person_count = len(persons_db.search_persons(conn, ""))
    except Exception:
        person_count = "?"
    try:
        frag_count = len(fragments_db.get_unsynced_fragments(conn, limit=9999))
    except Exception:
        frag_count = "?"
    try:
        sources_db.lookup_sources(conn, limit=1)
        source_note = "connected"
    except Exception:
        source_note = "unavailable"
    lines = [
        f"mode:    `{state.mode.value}`",
        f"skin:    `{state.skin}`",
        f"persons: {person_count}",
        f"stash:   {frag_count} unsynced fragments",
        f"sources: {source_note}",
        f"port:    8425",
    ]
    return result_block("status", "\n".join(lines))
