"""
Squirrel Responder — wires state, dispatcher, command handlers, and file writes.
"""
from responder.state import AppState, Mode
from responder.dispatcher import parse_command
from responder.formatter import result_block
from responder.commands import person, relationship, tree, fragment, source, search, gedcom, control


def make_responder(state: AppState):
    def handle(line: str):
        cmd = parse_command(line)
        if cmd is None:
            if state.mode == Mode.CHAT:
                _llm_chat(state, line)
            elif state.mode == Mode.LISTENING:
                _llm_hint(state, line)
            return
        try:
            result = _dispatch(cmd, state)
        except Exception as e:
            result = result_block("Error", f"```\n{e}\n```")
        if result:
            state.append(result)
    return handle


def _llm_chat(state, line):
    try:
        from responder.llm.chat import respond
        from db import get_connection, release_connection
        conn = get_connection()
        try:
            r = respond(conn, line)
            if r:
                state.append(r)
        finally:
            release_connection(conn)
    except Exception as e:
        state.append(result_block("Jeles (error)", str(e)))


def _llm_hint(state, line):
    try:
        from responder.llm.listener import maybe_hint
        from db import get_connection, release_connection
        conn = get_connection()
        try:
            hint = maybe_hint(conn, line)
            if hint:
                state.append(hint)
        finally:
            release_connection(conn)
    except Exception:
        pass


def _dispatch(cmd, state: AppState) -> str:
    name = cmd.name
    if name == "mode":
        return control.cmd_mode(state, cmd.args)
    if name == "skin":
        return control.cmd_skin(state, cmd.args)
    if name == "search":
        return search.cmd_search(cmd.args)
    if name == "unknown":
        return result_block("Unknown command", f"No handler for: `{cmd.raw}`")

    from db import get_connection, release_connection
    conn = get_connection()
    try:
        if name == "add person":       return person.cmd_add_person(conn, cmd.args)
        if name == "show person":      return person.cmd_show_person(conn, cmd.args)
        if name == "show people":      return person.cmd_show_people(conn, cmd.args)
        if name == "edit person":      return person.cmd_edit_person(conn, cmd.args)
        if name == "link":             return relationship.cmd_link(conn, cmd.args)
        if name == "show kin":         return relationship.cmd_show_kin(conn, cmd.args)
        if name == "tree":             return tree.cmd_tree(conn, cmd.args)
        if name == "stash":            return fragment.cmd_stash(conn, cmd.args)
        if name == "show stash":       return fragment.cmd_show_stash(conn, cmd.args)
        if name == "bind fragment":    return fragment.cmd_bind_fragment(conn, cmd.args)
        if name == "find sources":     return source.cmd_find_sources(conn, cmd.args)
        if name == "export gedcom":    return gedcom.cmd_export_gedcom(conn, cmd.args)
        if name == "import gedcom":    return gedcom.cmd_import_gedcom(conn, cmd.args)
        if name == "status":           return control.cmd_status(conn, state)
        return result_block("Unknown", f"No handler for `{name}`")
    finally:
        release_connection(conn)
