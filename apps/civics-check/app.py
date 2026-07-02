#!/usr/bin/env python3
"""Civics Check — America's 250th civics fair.

SAFE entry point: ``make run app=civics-check`` launches the Textual fair when
Textual is installed; use ``--cli`` for the stdlib fair map. Prefer ``./dev.sh`` for
a self-contained venv + catalog rebuild.

The CLI mirrors the TUI fair map: lanes → pavilions → catalog activities via
``ActivitySession`` (same grading, pools, and pass rules as the Textual stage).
"""
from __future__ import annotations

import sys

import bell
import db
import engine
import tui_art
from civics.session import ActivitySession

RED = "\033[91m"
GOLD = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

BANNER = f"""{bell.LIBERTY_BELL}{BOLD}
     C I V I C S   C H E C K
     America's 250th — Freedom 250 fair
{RESET}"""

TIER_ICON = tui_art.PAVILION_ICONS


def pause(msg: str = "(press enter to continue)") -> None:
    try:
        input(f"{DIM}{msg}{RESET}\n")
    except (KeyboardInterrupt, EOFError):
        raise


def header(title: str) -> None:
    print(f"\n{BOLD}{GOLD}--- {title} ---{RESET}\n")


def format_source(source: str) -> str:
    resolved = engine.resolve_source(source)
    if resolved:
        return f"{DIM}Source: {resolved['label']} — {resolved['url']}{RESET}"
    return f"{DIM}Source: {source}{RESET}"


def print_fair_intro() -> None:
    print(BANNER)
    playbill = engine.fair_playbill()
    if playbill.get("fair_day"):
        print(f"{GOLD}Today's pavilion: {playbill['fair_day']}{RESET}")
    if playbill.get("number_line"):
        print(f"{DIM}By the numbers: {playbill['number_line']}{RESET}")
    if playbill.get("motto"):
        print(f"{DIM}{playbill['motto']}{RESET}")
    if playbill.get("on_this_day"):
        print(f"{GOLD}On this day: {playbill['on_this_day']}{RESET}")
    if playbill.get("ticker"):
        print(f"{DIM}~~~ {playbill['ticker']} ~~~{RESET}")
    print()


def print_record_room() -> None:
    header("The Record Room")
    print(
        f"{DIM}Every fact in this fair came from somewhere. "
        f"These are the somewheres — and every one is a fine place to keep going.{RESET}\n"
    )
    links = engine.load_source_links()
    print(f"{BOLD}WHERE WE GOT THE INFO{RESET}")
    for r in links.get("resolvers", []):
        print(f"\n  ⧉ {r['label']}")
        if r.get("blurb"):
            print(f"    {r['blurb']}")
        print(f"    {DIM}{r['url']}{RESET}")
    print(f"\n{BOLD}LEARN MORE HERE{RESET}")
    for m in links.get("more", []):
        print(f"\n  ⧉ {m['label']}")
        if m.get("blurb"):
            print(f"    {m['blurb']}")
        print(f"    {DIM}{m['url']}{RESET}")
    pause()


def fireworks() -> None:
    for f in ["  .  *  .  ", "  * *** *  ", " *  *#*  * ", "  * *** *  ", "  .  *  .  "]:
        print(f"{RED}{f}{RESET}")


def finish_session(activity_id: str, session: ActivitySession) -> None:
    summary = session.summary()
    elapsed = summary.get("elapsed_s")
    print(f"\n{bell.telegram(activity_id, summary['score'], summary['total'], elapsed)}\n")
    if summary["total"] and summary["score"] == summary["total"]:
        fireworks()
        print(bell.perfect())
    db.record_score(activity_id, summary["score"], summary["total"], elapsed)


def _print_step(session: ActivitySession, step: dict) -> None:
    kind = session.kind
    if kind == "browse":
        print(f"{BOLD}{step.get('title', '')}{RESET}")
        if step.get("subtitle"):
            print(f"{DIM}{step['subtitle']}{RESET}")
        print(f"\n{step.get('body', '')}")
        if step.get("context"):
            print(f"\n{DIM}{step['context']}{RESET}")
        if step.get("source"):
            print(f"\n{format_source(step['source'])}")
        n = session.index + 1
        print(f"\n{DIM}[{n}/{session.total} — Enter for next]{RESET}")
        return

    if kind in ("quiz", "duel", "states"):
        if kind == "duel" and session._duel_players:
            player = session.duel_player() or ""
            sub = f"{player}'s turn"
        else:
            sub = step.get("category", "") or kind
        print(f"{BOLD}{step.get('question') or step.get('prompt', '')}{RESET}")
        print(f"{DIM}{sub} · Q {session.index + 1}/{session.total} · score {session.score}{RESET}")
        return

    if kind in ("pick", "match"):
        prompt = step.get("prompt") or step.get("quote", "")
        print(f"{BOLD}{prompt}{RESET}\n")
        for i, opt in enumerate(step.get("options", []), 1):
            print(f"  {i}. {opt}")
        print(f"\n{DIM}Q {session.index + 1}/{session.total}{RESET}")
        return

    if kind == "sort":
        print(f"{BOLD}Timeline Sort{RESET}\nPut these in chronological order (earliest first).\n")
        for num, label in step.get("items", []):
            print(f"  {num}. {label}")
        print(f"\n{DIM}Type numbers space-separated, e.g. 3 1 2 4{RESET}")


def run_activity(activity_id: str, title: str) -> None:
    """Run one catalog activity — same session engine as the Textual stage."""
    header(title)
    lane_id, _ = engine.activity_lane_pavilion(activity_id)
    lane_label = tui_art.LANE_ICONS.get(lane_id, "")
    if lane_label:
        print(f"{DIM}{lane_label}{RESET}\n")
    if activity_id in tui_art.NAT_ACTIVITY_IDS or lane_id == "citizenship_court":
        print(f"{DIM}Passing score: 6 of 10 on naturalization-style rounds.{RESET}\n")

    try:
        session = ActivitySession(activity_id)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Could not start activity: {exc}")
        pause()
        return

    if session.kind == "duel":
        try:
            p1 = input("Player 1 name> ").strip() or "Player 1"
            p2 = input("Player 2 name> ").strip() or "Player 2"
        except (KeyboardInterrupt, EOFError):
            return
        session.setup_duel(p1, p2)

    if activity_id == "missed":
        if not db.missed_card_ids(1) and not db.missed_question_ids(1):
            print("Nothing missed yet — clean slate.")
            pause()
            return


    while True:
        step = session.current()
        if step is None:
            finish_session(activity_id, session)
            pause()
            return

        _print_step(session, step)

        try:
            if session.kind == "browse":
                raw = input("\n> ").strip()
            else:
                raw = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted.")
            return

        if raw == "1776":
            print(f"{GOLD}THE BELL: Still not the answer.{RESET}")
            continue

        submit_arg = raw if session.kind != "browse" else (raw or " ")
        result = session.submit(submit_arg)

        if result.get("timed_out"):
            finish_session(activity_id, session)
            pause()
            return

        if session.kind == "browse":
            if result.get("done"):
                finish_session(activity_id, session)
                pause()
            continue

        if session.kind == "sort" and result.get("done"):
            print(f"\nScore {result.get('score', 0)}/{result.get('total', 0)}")
            for entry in result.get("ordered", []):
                print(f"  {entry['year']} — {entry['event']}")
            db.record_score(activity_id, result.get("score", 0), result.get("total", 0), session.elapsed())
            pause()
            return

        card_id = result.get("card_id")
        if card_id and session.kind in ("quiz", "duel", "states"):
            if result.get("correct"):
                db.clear_miss(card_id)
            else:
                db.record_miss(card_id)

        if result.get("correct"):
            print(bell.right())
            fact = result.get("fact") or result.get("person", "")
            if fact:
                print(f"  {DIM}{fact}{RESET}")
        else:
            print(bell.wrong())
            expected = result.get("expected", "")
            if isinstance(expected, list):
                expected = ", ".join(str(x) for x in expected)
            if expected:
                print(f"  {DIM}Accepted: {expected}{RESET}")

        if result.get("done"):
            if session.kind == "duel" and session._duel_scores:
                ds = session._duel_scores
                print(f"\n{BOLD}Final:{RESET} " + " · ".join(f"{k}: {v}" for k, v in ds.items()))
            finish_session(activity_id, session)
            pause()
            return


def pick_activity_for_pavilion(pavilion: dict) -> str | None:
    if pavilion["id"] == "_sources":
        print_record_room()
        return None
    menu = engine.pavilion_activity_menu(pavilion["id"])
    if len(menu) > 1:
        header(pavilion["label"])
        if pavilion.get("subtitle"):
            print(f"{DIM}{pavilion['subtitle']}{RESET}\n")
        for i, (act_id, label, kind) in enumerate(menu, 1):
            print(f"  {i}. {label}  [{kind}]")
        print(f"  {DIM}Enter — default activity{RESET}")
        try:
            raw = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            return None
        if not raw:
            act_id = engine.primary_activity_id(pavilion["id"])
            return act_id
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(menu):
                return menu[idx][0]
        except ValueError:
            pass
        print("Not a valid choice.")
        return None
    return engine.primary_activity_id(pavilion["id"])


def browse_lane(lane: dict) -> None:
    pavs = engine.pavilions_for_lane(lane["id"])
    if not pavs:
        print("No tents on this lane yet.")
        pause()
        return

    while True:
        lane_label = tui_art.LANE_ICONS.get(lane["id"], lane["label"])
        header(lane_label)
        for i, p in enumerate(pavs, 1):
            tier = p.get("default_tier", "show")
            icon = TIER_ICON.get(tier, "·")
            sub = p.get("subtitle", "")
            line = f"  {i}. {icon}  {p['label']}"
            if sub:
                line += f"  {DIM}— {sub}{RESET}"
            print(line)
        print(f"\n  {DIM}B — back to lanes · Q — quit fair{RESET}")
        try:
            raw = input("\n> ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            return
        if raw in ("B", "BACK"):
            return
        if raw == "Q":
            raise KeyboardInterrupt
        try:
            idx = int(raw) - 1
        except ValueError:
            print("Pick a pavilion number.")
            continue
        if not (0 <= idx < len(pavs)):
            print("Not a valid pavilion.")
            continue
        pavilion = pavs[idx]
        activity_id = pick_activity_for_pavilion(pavilion)
        if activity_id:
            run_activity(activity_id, pavilion["label"])


def fair_map_loop() -> None:
    lanes = engine.lanes_for_fair()
    while True:
        header("Freedom 250 Fair Map")
        print(f"{DIM}Pick a lane, then a pavilion — same tents as the Textual fair.{RESET}\n")
        for i, ln in enumerate(lanes, 1):
            label = tui_art.LANE_ICONS.get(ln["id"], ln["label"])
            print(f"  {i}. {label}")
        print(f"\n  S. Recent scores")
        print(f"  {DIM}109 — underground (if you know) · Q — quit{RESET}")
        try:
            raw = input("\n> ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            raise
        if raw == "Q":
            return
        if raw == "S":
            show_scores()
            continue
        if raw == "109":
            cat = engine.get_catalog()
            ug = next((ln for ln in cat.lanes if ln["id"] == "underground"), None)
            if ug:
                browse_lane(ug)
            else:
                print(f"{DIM}The floor beneath Liberty Plaza is not load-bearing.{RESET}")
                pause()
            continue
        try:
            idx = int(raw) - 1
        except ValueError:
            print("Pick a lane number, S for scores, or Q to quit.")
            continue
        if not (0 <= idx < len(lanes)):
            print("Not a valid lane.")
            continue
        browse_lane(lanes[idx])


def show_scores() -> None:
    header("Recent Scores")
    activity_ids = sorted({a["id"] for a in engine.activities()})
    any_rows = False
    for mode in activity_ids:
        rows = db.top_scores(mode, limit=3)
        if not rows:
            continue
        any_rows = True
        pav_id = engine.get_catalog().activity(mode)
        label = mode
        if pav_id:
            pid = pav_id.get("pavilion", mode)
            pav = engine.pavilion(pid)
            if pav:
                label = pav.get("label", mode)
        print(f"\n{BOLD}{label}{RESET} ({mode})")
        for score, total, elapsed_s, played_at in rows:
            t = f", {elapsed_s:.1f}s" if elapsed_s else ""
            print(f"  {score}/{total}{t}  ({played_at})")
    if not any_rows:
        print("No scores recorded yet — visit a pavilion first.")
    pause()


def main() -> None:
    """Launch fair TUI when Textual is available; otherwise stdlib fair map."""
    if "--cli" in sys.argv:
        _cli_main()
        return
    from tui import TEXTUAL_OK, main as tui_main

    if TEXTUAL_OK:
        tui_main()
        return
    print(
        "Textual is not installed.\n"
        "  pip install -r requirements.txt\n"
        "  ./dev.sh\n"
        "Starting CLI fair map instead.\n"
    )
    _cli_main()


def _cli_main() -> None:
    print_fair_intro()
    try:
        fair_map_loop()
    except (KeyboardInterrupt, EOFError):
        pass
    print("\nHappy 250th.")


if __name__ == "__main__":
    main()
