from pathlib import Path
from datetime import datetime
from responder.formatter import result_block
from gedcom.exporter import export
from gedcom.importer import import_ged

def cmd_export_gedcom(conn, args: list) -> str:
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
    count = import_ged(conn, path)
    return result_block("import gedcom",
        f"✓ {count} persons imported as fragments\nRun `@squirrel: bind fragment all` to promote matches.")
