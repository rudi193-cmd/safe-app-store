from pathlib import Path
from datetime import datetime
from responder.formatter import result_block
from gedcom.exporter import export
from gedcom.importer import import_ged
import sap.core.gate as _gate

def cmd_export_gedcom(conn, args: list) -> str:
    # PII leaves the box here — gate on export, not just read. The trust
    # table denies this outright to the jeles (LLM) actor.
    _gate.authorized("export")
    date_str = datetime.now().strftime("%Y%m%d")
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    out_path = desktop / f"squirrel_export_{date_str}.ged"
    count = export(conn, out_path)
    return result_block("export gedcom", f"✓ {count} persons exported\n`{out_path}`")

def cmd_import_gedcom(conn, args: list) -> str:
    if not args:
        return result_block("import gedcom", "Usage: `@squirrel: import gedcom /path/to/file.ged`")
    path = Path(" ".join(args)).expanduser()
    if not path.exists():
        return result_block("import gedcom", f"File not found: `{path}`")
    if not path.is_file():
        # B-010: a directory passes exists(); say so instead of surfacing a raw
        # [Errno 21] from import_ged.
        return result_block("import gedcom", f"Not a readable file: `{path}` "
                            "(is it a directory?)")
    count = import_ged(conn, path)
    return result_block("import gedcom",
        f"✓ {count} persons imported as fragments\nRun `@squirrel: bind fragment all` to promote matches.")
