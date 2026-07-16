"""
B-004 (explicit --person for stash) and B-010 (friendly non-file import
message) — the last two open items in the log.
"""
import pytest

from db import get_connection, release_connection
from responder.commands.fragment import parse_stash_args, cmd_stash
from responder.commands.gedcom import cmd_import_gedcom


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    release_connection(c)


# ── B-004 ─────────────────────────────────────────────────────────────────────

def test_explicit_person_flag_wins_over_heuristic(conn):
    # Fragment text does NOT lead with the name; quoted --person names it.
    out = cmd_stash(conn, ['The', 'quilt', 'is', 'hers', '--person', '"Fern', 'Nutkin"'])
    assert "for **Fern Nutkin**" in out
    import db.fragments as F
    frag = F.search_fragments(conn, "quilt")[0]
    assert frag["person_name"] == "Fern Nutkin"     # not "The quilt"


def test_person_flag_multiword_and_quoted(conn):
    parsed = parse_stash_args(['note', '--person', '"Oscar', 'Mann"'])
    assert parsed["person_name"] == "Oscar Mann"


def test_heuristic_still_the_fallback(conn):
    out = cmd_stash(conn, ['Oscar', 'Mann', 'kept', 'letters'])
    assert "for **Oscar Mann**" in out              # first two words, as before


def test_unquoted_person_takes_one_token_not_the_story(conn):
    # The review bug: an unquoted flag must NOT swallow the trailing story.
    parsed = parse_stash_args('--person Oscar kept letters and photos'.split())
    assert parsed["person_name"] == "Oscar"
    assert parsed["story_text"] == "kept letters and photos"


def test_source_flag_stays_single_token(conn):
    # --source was single-token before B-004; it must stay that way unquoted.
    parsed = parse_stash_args(
        'Grandma told us --source oral history that she crossed in 1952'.split())
    assert parsed["source"] == "oral"
    assert parsed["story_text"] == "Grandma told us history that she crossed in 1952"


def test_quoted_person_midcommand_does_not_eat_story(conn):
    parsed = parse_stash_args(['--person', '"Ada', 'Lovelace"', 'wrote', 'the', 'first', 'program'])
    assert parsed["person_name"] == "Ada Lovelace"
    assert parsed["story_text"] == "wrote the first program"


def test_person_flag_does_not_leak_into_story(conn):
    parsed = parse_stash_args(['a', 'memory', '--person', '"Ada', 'Lovelace"', '--confidence', 'likely'])
    assert parsed["story_text"] == "a memory"
    assert parsed["person_name"] == "Ada Lovelace"
    assert parsed["confidence"] == "likely"


def test_person_flag_at_end_with_no_value(conn):
    parsed = parse_stash_args(['some', 'text', '--person'])   # dangling flag
    assert parsed.get("person_name", "") == ""
    assert parsed["story_text"] == "some text"


# ── B-010 ─────────────────────────────────────────────────────────────────────

def test_import_directory_gives_friendly_message(conn, tmp_path):
    out = cmd_import_gedcom(conn, [str(tmp_path)])   # a directory
    assert "Not a readable file" in out
    assert "Errno" not in out                        # no raw errno


def test_import_missing_still_says_not_found(conn, tmp_path):
    out = cmd_import_gedcom(conn, [str(tmp_path / "nope.ged")])
    assert "File not found" in out
