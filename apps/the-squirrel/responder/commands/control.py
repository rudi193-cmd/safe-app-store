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


def cmd_receipts(args: list) -> str:
    """Self-audit: the local tool-call trail, newest first.

    `@squirrel: receipts [N] [actor]` — N rows (default 20); optional actor
    filter (journal | jeles | bypass | unattributed).
    """
    from sap.core import receipts as receipts_log
    limit = 20
    actor = None
    aliases = {"journal": "squirrel-journal", "jeles": "squirrel-jeles",
               "bypass": "operator-bypass", "unattributed": "unattributed"}
    for a in args:
        if a.isdigit():
            limit = int(a)
        elif a.lower() in aliases:
            actor = aliases[a.lower()]
    rows = receipts_log.tail(app_id=actor, limit=limit)
    if not rows:
        return result_block("receipts", "_No receipts yet._")
    lines = ["| when (UTC) | who | tool | outcome | detail |",
             "|---|---|---|---|---|"]
    for r in rows:
        when = r["ts"][:19].replace("T", " ")
        detail = (r["detail"] or "").replace("|", "\\|")[:60]
        lines.append(f"| {when} | {r['app_id']} | {r['tool']} | "
                     f"{r['outcome']} | {detail} |")
    return result_block("receipts", "\n".join(lines))


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
    try:
        from sap.core import vault
        if (vault.squirrel_home() / "vault.db").exists():
            vault_note = f"{len(vault.default_vault().list_keys())} secrets"
        else:
            vault_note = "not provisioned"
    except Exception as e:
        vault_note = f"unavailable ({e.__class__.__name__})"
    try:
        from responder.llm.chat import _ollama_available
        jeles_note = "ready (Ollama local)" if _ollama_available() else \
                     "offline — journal mode only (install Ollama to invite Jeles in)"
    except Exception:
        jeles_note = "offline — journal mode only"
    lines = [
        f"mode:    `{state.mode.value}`",
        f"skin:    `{state.skin}`",
        f"persons: {person_count}",
        f"stash:   {frag_count} unsynced fragments",
        f"sources: {source_note}",
        f"vault:   {vault_note}",
        f"jeles:   {jeles_note}",
        f"port:    8425",
    ]
    return result_block("status", "\n".join(lines))
