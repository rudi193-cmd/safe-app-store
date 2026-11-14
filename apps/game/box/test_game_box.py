"""The game box: a table laid with nothing sealed, a night played through
every piece under the seal of whoever holds the key, and the table's own
check finding a forged row. The key here is the test's, made in a scratch
folder; the test plays the person who rules the table."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
sys.path.insert(0, str(ROOT))
import kernel

STDLIB = ROOT / "adapters" / "stdlib"
NOW = ["--now", "2026-11-14T10:00:00Z"]


def py(*argv) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *map(str, argv)], capture_output=True, text=True, check=False
    )


class Table:
    def __init__(self, tmp: Path):
        self.dir, self.key = tmp / "table", tmp / "gm.key"
        self.box, self.pile = self.dir / "record", self.dir / "pile"
        self.world = self.dir / "worlds" / "lantern-fair.json"

    def open(self):
        return py(
            HERE / "open_table.py", "open", "--table", self.dir, "--key", self.key, *NOW
        )

    def check(self):
        return py(HERE / "open_table.py", "check", "--table", self.dir)

    def k(self, *argv):
        return py(ROOT / "kernel.py", argv[0], "--box", self.box, *NOW, *argv[1:])

    def addon(self, name: str, *argv):
        script = STDLIB / name / f"{name.replace('-', '_')}.py"
        return py(script, *argv)

    def gm(self, *argv):
        return self.addon(
            "game-master", "--box", self.box, *argv, "--world", self.world, *NOW
        )

    def checkers(self, *argv):
        return self.addon("checkers", "--box", self.box, *argv, *NOW)

    def rows(self) -> list[dict]:
        return kernel.read(self.box / "record.jsonl")[0]

    def waiting(self) -> list[str]:
        sealed = {r["subject"] for r in self.rows() if r["kind"] in ("seal", "decline")}
        return [r["subject"] for r in self.rows()
                if r["kind"] == "proposal" and r.get("verdict") == "pass" and r["subject"] not in sealed]  # fmt: skip

    def seal(self, subject: str):
        got = self.k("seal", subject)
        assert got.returncode == 0, got.stderr

    def session(self, *argv, world: str = "clockwork-cellar"):
        return py(
            HERE / "session.py", "--table", self.dir, "--world", world, *argv, *NOW
        )

    def asked(self) -> list[str]:
        """The rulings handed in that nobody has answered."""
        said = {r["subject"] for r in self.rows() if r["kind"] in ("seal", "decline")}
        return [r["subject"] for r in self.rows() if r["kind"] == "table-ask" and r["subject"] not in said]  # fmt: skip

    def night(self, answer=lambda fact: True, world: str = "clockwork-cellar"):
        """Play a session to its end, the test standing in for the person:
        each ruling the story reaches is sealed or declined by `answer`."""
        for _ in range(20):
            got = self.session(world=world)
            if got.returncode != 42:
                return got
            for subj in self.asked():
                fact = next(r["fact"] for r in self.rows() if r.get("subject") == subj and r["kind"] == "table-ask")  # fmt: skip
                assert (
                    self.k("seal" if answer(fact) else "decline", subj).returncode == 0
                )
        raise AssertionError("the session never ended")

    def beats(self) -> list[str]:
        return [f"{r['beat']}:{r.get('band') or r.get('verdict')}" for r in self.rows() if r["kind"] == "table-beat"]  # fmt: skip


@pytest.fixture
def t(tmp_path):
    return Table(tmp_path)


def test_open_lays_a_table_and_seals_nothing(t):
    got = t.open()
    assert got.returncode == 42, got.stderr
    assert "7 waiting on the seal, nothing sealed" in got.stdout
    kinds = [r["kind"] for r in t.rows()]
    assert kinds.count("proposal") == 7 and "table-open" in kinds
    assert not [
        r
        for r in t.rows()
        if r["kind"] in ("seal", "decline") or r.get("who") == "human"
    ]
    assert t.key.exists() and not any(p.name == t.key.name for p in t.dir.rglob("*"))
    assert sorted(p.name for p in t.pile.iterdir()) == ["house-rules.md", "monsters", "people", "sessions"]  # fmt: skip
    assert (
        t.dir / "words.txt"
    ).stat().st_mode & 0o077 == 0  # the words list, owner-only, beside the pile
    assert (t.dir / "check.md").is_file() and (t.dir / "gm-stack.md").is_file()
    assert sorted(p.name for p in (t.dir / "worlds").iterdir()) == [
        "aetheris.json", "clockwork-cellar.json", "hasbeen.json", "ironworks.json", "lantern-fair.json"]  # fmt: skip
    assert (t.dir / "stories" / "wasp-nest.md").is_file()
    assert t.k("verify").returncode == 0


def test_the_check_page_says_what_waits_until_the_rules_are_sealed(t):
    t.open()
    got = t.check()
    assert got.returncode == 42 and "1 of 5 steps flagged (exit 42)" in got.stdout
    assert len(re.findall(r"waiting +the rule", got.stdout)) == 7
    for subj in t.waiting():
        t.seal(subj)
    got = t.check()
    assert got.returncode == 0 and "0 of 5 steps flagged (exit 0)" in got.stdout
    assert len(re.findall(r"sealed +the rule", got.stdout)) == 7


def test_a_night_at_the_table_through_every_piece(t):
    t.open()
    for subj in t.waiting():  # the house rules, sealed by whoever rules the table
        t.seal(subj)
    rule = t.addon("rules", "ask", "--box", t.box, *NOW, "Draws")
    assert rule.returncode == 0 and "ruled by whoever rules the table" in rule.stdout

    # the story: two actions, a ruling sealed, one more action, a ruling declined
    for argv in (("act", "Grit"), ("act", "Wit"), ("ask",)):
        assert t.gm(*argv).returncode in (0, 42)
    t.seal(t.waiting()[0])
    assert t.gm("settle").returncode == 0
    assert t.gm("act", "Heart").returncode == 0
    assert t.gm("ask").returncode == 42
    assert t.k("decline", t.waiting()[0]).returncode == 0
    end = t.gm("settle")
    assert end.returncode == 0 and "finished" in end.stdout

    # checkers: a few moves, a draw offered, and the ruler seals it
    assert t.checkers("new").returncode == 0
    for m in ("11-15", "23-19", "8-11", "22-17"):
        assert t.checkers("move", m).returncode == 0
    assert t.checkers("offer").returncode == 42
    t.seal(t.waiting()[0])
    assert "a draw" in t.checkers("settle").stdout

    # a logic grid, seeded by the record's tip
    assert t.addon("catgrid", "--box", t.box, "play", *NOW).returncode == 0

    got = t.check()
    assert got.returncode == 0, got.stdout
    for says in ("1 game, 5 beats, 3 rolls", "1 game of checkers", "1 game on the record", "3 rolls on the record"):  # fmt: skip
        assert says in got.stdout, says
    assert "the chain holds" in got.stdout
    seals = [r for r in t.rows() if r["kind"] == "seal"]
    assert len(seals) == 9 and {r["who"] for r in seals} == {
        "human"
    }  # 7 rules, a ruling, a draw


def test_a_forged_move_is_caught_by_the_tables_own_check(t):
    t.open()
    assert t.checkers("new").returncode == 0
    game = [r for r in t.rows() if r["kind"] == "checkers-open"][-1]["n"]
    kernel.append(t.box, NOW[1], "checkers-move", who="checkers", game=game, ply=0,
                  side="black", move="11-14", result="on")  # fmt: skip
    got = t.check()
    assert got.returncode == 42
    assert "checkers -- --box {box} check`  (exit 2)" in got.stdout
    assert "isn't a move black may make" in got.stdout


def test_an_edited_row_breaks_the_chain_and_the_check_says_so(t):
    t.open()
    raw = (t.box / "record.jsonl").read_bytes()
    (t.box / "record.jsonl").write_bytes(
        raw.replace(b"Lantern Fair", b"Lantern Fail", 1)
    )
    got = t.check()
    assert got.returncode == 2 and "the chain" in got.stderr


def test_open_refuses_a_table_already_there_or_a_key_inside_it(t, tmp_path):
    t.dir.mkdir()
    got = t.open()
    assert got.returncode == 2 and "already there" in got.stderr
    inside = py(HERE / "open_table.py", "open", "--table", tmp_path / "t2", "--key", tmp_path / "t2" / "k", *NOW)  # fmt: skip
    assert inside.returncode == 2 and "outside the box" in inside.stderr
    assert not (tmp_path / "t2").exists()


def test_a_command_line_that_isnt_one_is_refused(t, tmp_path):
    for argv in (
        (),
        ("open",),
        ("fly", "--table", "x"),
        ("open", "--table", str(tmp_path / "x")),
    ):
        assert py(HERE / "open_table.py", *argv).returncode == 2
    for page in ("check", "prep"):
        got = py(HERE / "open_table.py", page, "--table", tmp_path / "nowhere")
        assert got.returncode == 2 and "isn't a box" in got.stderr


@pytest.mark.parametrize("name", ["lantern-fair", "clockwork-cellar"])
def test_each_world_is_one_game_master_takes_and_names_no_player(name):
    world = json.loads((HERE / "worlds" / f"{name}.json").read_text())
    assert "never a player" in world["setting"]
    sys.path.insert(0, str(STDLIB / "game-master"))
    import game_master

    game_master.validate(world)


# ── a session played by code ─────────────────────────────────────────────────
def test_a_session_plays_to_the_first_ruling_and_waits(t):
    t.open()
    got = t.session()
    assert got.returncode == 42 and "it waits on you" in got.stdout
    assert [b.split(":")[0] for b in t.beats()] == ["stair", "gears"]
    assert len(t.asked()) == 1
    again = t.session()  # nothing answered: it says so, and plays nothing more
    assert again.returncode == 42 and len(t.beats()) == 2


def test_a_whole_session_ends_with_what_the_table_made_true(t):
    t.open()
    got = t.night()
    assert got.returncode == 0, got.stderr
    assert "The Clockwork Cellar, played to its end" in got.stdout
    assert "button  sealed" in got.stdout and "guest  sealed" in got.stdout
    canon = t.session("canon")
    assert canon.returncode == 0 and "what this table holds true:" in canon.stdout
    assert "the Lantern Man" in canon.stdout
    check = t.check()
    assert (
        "2 games, " in check.stdout and "every one holds" in check.stdout
    )  # the fair, opened, and the cellar


def test_canon_never_frees_the_prince_unless_a_riddle_was_answered(t):
    """Whatever the dice did tonight, the rulings put to the person are the
    ones the story reached."""
    t.open()
    t.night()
    path = t.beats()
    canon = t.session("canon").stdout
    answered = any(b in path for b in ("riddle:strong", "riddle:weak", "second:strong", "second:weak"))  # fmt: skip
    assert ("Prince Aldric is free" in canon) == answered, path
    if "riddle:miss" not in path:
        assert not any(b.startswith("second") for b in path)


@pytest.mark.parametrize(
    "heart, path",
    [
        (10, ["riddle:strong", "free:sealed"]),
        (-10, ["riddle:miss", "second:"]),
    ],
)
def test_the_riddle_roll_turns_the_story(t, heart, path):
    """A copy of the cellar whose Brann always answers (or never does)."""
    t.open()
    f = t.dir / "worlds" / "clockwork-cellar.json"
    w = json.loads(f.read_text())
    next(c for c in w["characters"] if c["id"] == "brann")["stats"]["Heart"] = heart
    f.write_text(json.dumps(w))
    assert t.night().returncode == 0
    got = t.beats()
    assert got[4] == path[0] and got[5].startswith(path[1]), got
    if heart < 0:
        assert "free:" not in " ".join(
            got
        )  # the first freeing is never put to the person


def test_a_ruling_said_no_to_is_canon_as_a_no(t):
    t.open()
    t.night(answer=lambda fact: "guest" not in fact)
    canon = t.session("canon").stdout
    assert (
        "what it said no to:" in canon and "not: A guest walks into the cellar" in canon
    )
    assert "The red button is bait" in canon.split("what it said no to:")[0]


def test_canon_before_anything_is_sealed_says_so(t):
    t.open()
    got = t.session("canon")
    assert got.returncode == 42 and "nothing has been sealed" in got.stdout


def test_the_table_cannot_read_the_script(t):
    """The worlds are beside the pile, never in it: asking the record about a
    scene not played yet, or a ruling not made, finds nothing to serve."""
    t.open()
    for q in ("is the red button bait", "is prince aldric free"):
        got = json.loads(t.k("bite", q).stdout)
        assert all("worlds/" not in s["where"] for s in got.get("served", [])), got


def test_a_session_refuses_what_isnt_a_table_or_a_world(t, tmp_path):
    t.open()
    assert "no world" in t.session(world="nowhere").stderr
    got = py(HERE / "session.py", "--table", tmp_path / "none")
    assert got.returncode == 2 and "isn't a table" in got.stderr
    for argv in ((), ("--table", str(t.dir), "fly")):
        assert py(HERE / "session.py", *argv).returncode == 2


# ── the game master's binder ─────────────────────────────────────────────────
def served(t, q: str) -> list[str]:
    return [s["where"] for s in json.loads(t.k("bite", q).stdout).get("served", [])]


@pytest.mark.parametrize(
    "question, first",
    [
        ("what are the clockwork hound's stats", "monsters/clockwork-hound.md:5"),
        ("how much damage does the dog do", "monsters/clockwork-hound.md:5"),
        ("how does cogwen talk", "people/cogwen.md:5"),
    ],
)
def test_the_binder_answers_the_gm_in_their_own_words(t, question, first):
    """The words list puts "stats" into grit, wit, hits; "dog" into hound."""
    t.open()
    assert served(t, question)[0] == first


def test_the_words_list_finds_the_prince_by_his_title(t):
    t.open()
    assert "sessions/2026-11-07.md:3" in served(
        t, "what does the prince want"
    )  # "Prince Aldric asked for his goats back"


def test_prep_runs_the_thirteen_steps_and_every_week_has_its_own_run(t):
    t.open()
    for week in ("001", "002"):
        got = py(HERE / "open_table.py", "prep", "--table", t.dir)
        assert got.returncode == 42, got.stderr  # the house rules wait on the seal
        run = t.dir / "prep" / week
        log = (run / "00-stack.txt").read_text()
        assert log.rstrip().endswith("done: 3 of 13 steps flagged"), log
        springs = (run / "springs.txt").read_text()
        assert "Next time: where the springs go." in springs
        assert "Juno pocketed one of Cogwen's springs" in springs
        assert (
            "Prince Aldric asked for his goats back" in (run / "prince.txt").read_text()
        )
    page = got.stdout
    assert 'first mention of "lantern man": 2026-10-31' in page
    assert "10+          7/12        58.33%" in page  # the hound's bite, 2d6+3
    assert "No gaps in 1 log with a rhythm." in page
    assert "the chain holds" in page


def test_prep_flags_a_week_missed(t):
    """gaps' 0 is a gap found: the page flags it, and a clean run it doesn't.
    A weekly log's gap is more than three weeks with no session notes."""
    t.open()
    py(HERE / "open_table.py", "prep", "--table", t.dir)
    log = (t.dir / "prep" / "001" / "00-stack.txt").read_text()
    assert "07 gaps: exit 42, 4 lines\n" in log  # no gap, not flagged
    (t.pile / "sessions" / "2026-12-12.md").write_text(
        "# Session, 12 December 2026\n\nBack after four weeks off.\n"
    )
    page = py(HERE / "open_table.py", "prep", "--table", t.dir).stdout
    log = (t.dir / "prep" / "002" / "00-stack.txt").read_text()
    line = next(x for x in log.splitlines() if x.startswith("07 gaps: exit"))
    assert line.startswith("07 gaps: exit 0") and line.endswith("flagged"), line
    assert "GAP       2026-11-14 to 2026-12-12" in page


# ── a guest invented on the night ────────────────────────────────────────────
VELL = "A guest comes down the stair: Old Vell from the lantern fair, looking for her lost lamp."


def test_a_guest_offered_on_the_night_is_canon_the_night_its_sealed(t):
    t.open()
    assert t.session().returncode == 42  # stair, gears, then the button waits
    got = t.session("offer", "pell", VELL)
    assert got.returncode == 42 and "Pell offers: " + VELL in got.stdout
    offer = [r for r in t.rows() if r["kind"] == "table-offer"][-1]
    assert "Old Vell" not in t.session("canon").stdout  # waiting is not canon
    t.seal(offer["subject"])
    played = t.night()  # the button, the written guest, the riddle: the story goes on
    assert played.returncode == 0, played.stderr
    assert any(r["kind"] == "table-heard" and r["subject"] == offer["subject"] and r["verdict"] == "sealed"
               for r in t.rows())  # fmt: skip
    canon = t.session("canon").stdout
    assert VELL + "  [offered by pell]" in canon.split("what it said no to:")[0]
    assert "The red button is bait" in canon
    assert "every one holds" in t.check().stdout


def test_an_offer_waits_without_stopping_the_story(t):
    t.open()
    t.session()
    t.session("offer", "juno", "The spring wasps wake when the cage opens.")
    before = len(t.beats())
    for subj in t.asked():  # the GM answers the story's rulings, not the offer
        t.seal(subj)
    assert t.session().returncode == 42 and len(t.beats()) > before
    assert [r for r in t.rows() if r["kind"] == "table-offer"] and not [r for r in t.rows() if r["kind"] == "table-heard"]  # fmt: skip


def test_an_offer_said_no_to_is_canon_as_a_no(t):
    t.open()
    t.session()
    t.session("offer", "brann", "Brann's goats can talk.")
    offer = [r for r in t.rows() if r["kind"] == "table-offer"][-1]
    assert t.k("decline", offer["subject"]).returncode == 0
    t.night()
    canon = t.session("canon").stdout
    assert "not: Brann's goats can talk.  [offered by brann]" in canon


def test_an_offer_is_a_seated_characters(t):
    t.open()
    t.session()
    got = t.session("offer", "cogwen", "Cogwen was a person once.")
    assert got.returncode == 2 and "isn't a seated character" in got.stderr


def test_a_guest_sealed_as_a_guest_gets_a_beat_of_their_own(t):
    """The cellar turns on a guest the table offered: sealed before the
    story's end, Brann asks the guest what they came down here for."""
    t.open()
    t.session()
    got = t.session("offer", "pell", VELL, "--as", "guest")
    assert got.returncode == 42
    t.seal([r for r in t.rows() if r["kind"] == "table-offer"][-1]["subject"])
    assert t.night().returncode == 0
    assert t.beats()[-1].startswith("stranger:")
    last = [r for r in t.rows() if r["kind"] == "table-beat"][-1]
    world = json.loads((t.dir / "worlds" / "clockwork-cellar.json").read_text())
    stranger = next(b for b in world["scenes"][1]["beats"] if b["id"] == "stranger")
    assert (
        last["character"] == "brann"
        and last["text"] == stranger["outcomes"][last["band"]]
    )
    assert "every one holds" in t.check().stdout


def test_with_no_guest_offered_the_cellar_has_no_stranger(t):
    t.open()
    t.night()
    assert not any(b.startswith("stranger:") for b in t.beats())


def test_an_offer_as_a_kind_the_cellar_doesnt_turn_on_is_refused(t):
    t.open()
    t.session()
    got = t.session("offer", "pell", VELL, "--as", "twist")
    assert got.returncode == 2 and "(it names: guest)" in got.stderr


# ── previously on ───────────────────────────────────────────────────────────
def test_recap_before_anything_says_nothing_is_true_yet(t):
    t.open()
    got = t.session("recap")
    assert "Nothing yet: the table hasn't made anything true." in got.stdout
    assert "Your notes from 2026-11-14:" in got.stdout  # the GM's own notes still come


def test_recap_reads_aloud_only_what_the_table_made_true_last_time_first(t):
    t.open()
    t.session()
    t.session("offer", "pell", VELL, "--as", "guest")
    for subj in t.asked() + [
        r["subject"] for r in t.rows() if r["kind"] == "table-offer"
    ]:
        t.seal(subj)
    t.session()  # the button ruling settled
    assert (
        py(STDLIB / "session-seal" / "session_seal.py", "--box", t.box, *NOW).returncode
        == 42
    )  # night one ends
    t.night()
    got = t.session("recap").stdout
    aloud, gm_only = got.split("## For the GM's eyes")
    last, rest = aloud.split("Last time:")[1].split("This time, so far:")
    assert "The red button is bait" in last and VELL in last
    assert "Prince Aldric is free" in rest
    for secret in (
        "Weakness",
        "smoke",
        "kids want it kept that way",
    ):  # the binder is the GM's
        assert secret not in aloud
    assert "sessions/2026-11-14.md:5  Next time: where the springs go." in gm_only
    assert (
        "sessions/2026-10-24.md:5  Brann wanted to bring a friend. I said next time."
        in gm_only
    )


# ── between sessions ─────────────────────────────────────────────────────────
def test_ideas_are_dealt_from_the_box_again_from_the_same_seed(t):
    t.open()
    t.night()
    first = py(HERE / "ideas.py", "--table", t.dir, "--seed", "between nights")
    again = py(HERE / "ideas.py", "--table", t.dir, "--seed", "between nights")
    seeds = lambda got: got.stdout.split("## Set up")[0]
    assert first.returncode == 0 and seeds(first) == seeds(again)
    dealt = [ln for ln in seeds(first).splitlines() if ln.startswith("  - ")]
    assert len(dealt) == 5
    for name in (
        "Tamsin",
        "Oro",
        "stalls",
    ):  # the cellar was played: its ideas, not the fair's
        assert name not in seeds(first)
    assert (
        "  - Spring wasps  (monsters/)" in first.stdout
    )  # set up in the binder, never in a session
    assert "Next time: where the springs go." in first.stdout
    assert "Something you wrote and forgot" in first.stdout


def test_a_story_written_as_markdown_is_a_world_game_master_plays(t):
    t.open()
    made = py(HERE / "author.py", t.dir / "stories" / "wasp-nest.md", "--to", t.dir / "worlds" / "wasp-nest.json")  # fmt: skip
    assert made.returncode == 0 and "The Wasp Nest, 2 scenes, 7 beats" in made.stdout
    got = t.night(world="wasp-nest")
    assert got.returncode == 0 and "The Wasp Nest, played to its end" in got.stdout
    played = [b.split(":")[0] for b in t.beats()]
    assert played[0] == "climb" and ("wasps" in played) == (
        t.beats()[0] != "climb:strong"
    )
    assert "guest" not in played  # no guest offered: that beat never comes
    again = py(HERE / "author.py", t.dir / "stories" / "wasp-nest.md", "--to", t.dir / "worlds" / "wasp-nest.json")  # fmt: skip
    assert again.returncode == 2 and "never written over" in again.stderr


@pytest.mark.parametrize(
    "text, says",
    [
        ("# A story\n\ncolour: blue\n", "line 3: 'colour' isn't a story's"),
        ("# A story\n## Characters\n- pell: Pell\n", "line 3: a character is"),
        (
            "# A story\n\n### A beat before any scene\n",
            "line 3: a beat comes inside a scene",
        ),
    ],
)
def test_a_story_that_isnt_one_is_refused_naming_its_line(tmp_path, text, says):
    (tmp_path / "s.md").write_text(text)
    got = py(HERE / "author.py", tmp_path / "s.md")
    assert got.returncode == 2 and says in got.stderr, got.stderr


def test_a_story_game_master_wouldnt_play_is_refused_with_its_reason(tmp_path):
    text = (
        (HERE / "stories" / "wasp-nest.md")
        .read_text()
        .replace("suggests: Wit", "suggests: Charm")
    )
    (tmp_path / "s.md").write_text(text)
    got = py(HERE / "author.py", tmp_path / "s.md")
    assert got.returncode == 2 and "'Charm' is not a stat" in got.stderr


@pytest.mark.parametrize("name", ["aetheris", "hasbeen", "ironworks"])
def test_the_tables_own_worlds_play_in_the_box(t, name):
    """The three worlds the-table authored in the store, as they are."""
    t.open()
    got = t.night(world=name)
    assert got.returncode == 0 and "played to its end" in got.stdout, got.stderr


def test_the_next_chapter_carries_what_the_last_one_made_true(t):
    """Played after a cellar whose prince the GM sealed free, the wasp nest
    opens with him coming to watch; with no cellar played, it never does."""
    t.open()
    f = t.dir / "worlds" / "clockwork-cellar.json"
    w = json.loads(f.read_text())
    next(c for c in w["characters"] if c["id"] == "brann")["stats"]["Heart"] = (
        10  # the riddle is answered
    )
    f.write_text(json.dumps(w))
    assert t.night().returncode == 0
    assert "Prince Aldric is free" in t.session("canon").stdout
    py(
        HERE / "author.py",
        t.dir / "stories" / "wasp-nest.md",
        "--to",
        t.dir / "worlds" / "wasp-nest.json",
    )
    assert t.night(world="wasp-nest").returncode == 0
    nest = [
        r["beat"]
        for r in t.rows()
        if r["kind"] == "table-beat" and r["scene"] == "up-into-the-ceiling"
    ]
    assert nest[0] == "prince"
    assert "every one holds" in t.check().stdout


# ── the play grows the world ─────────────────────────────────────────────────
def test_export_canon_writes_only_what_was_sealed_with_its_seal(t):
    t.open()
    assert t.session("export-canon").returncode == 42  # nothing sealed yet
    t.session()
    t.session("offer", "pell", VELL, "--as", "guest")
    t.seal([r for r in t.rows() if r["kind"] == "table-offer"][-1]["subject"])
    t.night(answer=lambda fact: "Lantern Man" not in fact)
    to = t.dir / "canon.md"
    got = t.session("export-canon", "--to", to)
    assert got.returncode == 0
    lines = to.read_text().splitlines()
    assert (
        lines[0]
        == f"<!-- canon from a game box: record {t.rows()[0]['hash']}, "
        + lines[0].split(", ")[1]
    )
    assert lines[1] == "# What the table made true"
    facts = [ln[2:] for ln in lines if ln.startswith("- ")]
    assert "The red button is bait: whoever leaves it alone wins the room." in facts
    assert VELL in facts
    assert not any("Lantern Man" in f for f in facts)  # declined: it stays in the box
    seals = [ln.strip() for ln in lines if ln.startswith("  sealed: proposal:")]
    assert len(seals) == len(facts)
    assert any(
        s.endswith("| clockwork-cellar, offered by pell as a guest") for s in seals
    )
    again = t.session("export-canon", "--to", to)
    assert again.returncode == 2 and "never written over" in again.stderr
