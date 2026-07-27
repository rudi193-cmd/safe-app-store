"""Smoke test for digest.build_digest — run from inside apps/nest-seed/."""
from nest_pipeline import db as _db
import digest as _digest


def test_build_digest_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("NEST_CACHE_DIR", str(tmp_path))  # isolate discovered store
    p = tmp_path / "t.db"
    conn = _db.open_db(p)
    _db.init_meta(conn, "Tester")
    conn.execute("insert into sources(path,filename,file_hash,ocr_method) "
                 "values('/a','a.md','h1','plaintext')")
    conn.executemany(
        "insert into fragments(source_id,fragment_type,content,label,confidence,date_ref)"
        " values(1,?,?,?,?,?)",
        [("document", "an overview of the system", "knowledge", "likely", ""),
         ("date", "2026-05-31", "", "likely", "2026-05-31"),
         ("date", "1970-01-01", "", "likely", "1970-01-01"),
         ("person", "David Martinez", "", "likely", "")])
    conn.commit()
    conn.close()

    md = _digest.build_digest(str(p))
    assert "# 🪺 Nest Digest" in md
    assert "## By category" in md and "knowledge" in md
    assert "David Martinez" in md
    assert "2026" in md
    # the lone 1970 date is reported as an epoch artifact, not in the span
    assert "epoch-zero" in md
