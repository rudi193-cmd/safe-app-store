"""
Red Flag Detection - Dating Wellbeing Core
15 behavioral categories. Returns (red_flags, yellow_flags) lists.
"""
from __future__ import annotations
from typing import NamedTuple


class FlagDef(NamedTuple):
    severity: str
    phrases: tuple
    explanation: str


FLAG_DEFS: dict = {
    "love_bombing": FlagDef("red", (
        "soulmate", "never felt this", "you're perfect", "move fast",
        "never met anyone like you", "meant to be", "you complete me",
        "my whole world", "don't need anyone else",
    ), "Excessive early intensity can mask controlling behavior ahead."),
    "control_possessiveness": FlagDef("red", (
        "don't waste my time", "where were you", "who were you with",
        "you're mine", "no one else", "not allowed to", "i'll decide",
        "you don't need friends", "they're bad for you", "can't trust you",
    ), "Possessive or controlling language early on is a serious warning sign."),
    "gaslighting": FlagDef("red", (
        "you're too sensitive", "you imagined that", "that never happened",
        "you're being paranoid", "you always do this", "you're crazy",
        "overreacting", "you misunderstood", "you're making it up",
    ), "Reality-denial patterns undermine trust and psychological safety."),
    "isolation_attempt": FlagDef("red", (
        "your friends are toxic", "your family doesn't understand",
        "they don't want you to be happy", "we don't need them",
        "cut them off", "they're jealous of us", "those people are bad influences",
    ), "Attempts to separate you from support networks are a core abuse tactic."),
    "boundary_violations": FlagDef("red", (
        "just this once", "if you loved me", "stop playing hard to get",
        "you're being uptight", "prove you trust me", "your boundaries are excuses",
    ), "Ignoring explicitly stated limits is non-negotiable."),
    "manipulation_tactics": FlagDef("red", (
        "i'll leave if you don't", "you'll regret this", "nobody else would want you",
        "i could find someone better", "you owe me", "after everything i've done",
        "you made me do this", "you're lucky i",
    ), "Threats, guilt-trips, and coercion replace genuine communication."),
    "entitlement": FlagDef("red", (
        "know what i want", "i deserve", "women owe me", "men owe me",
        "you should feel lucky", "most people can't handle me",
        "i'm not like other guys", "i'm not like other girls",
        "all women are", "all men are", "high value",
    ), "Entitlement correlates strongly with disregard for your needs."),
    "age_gap_rationalize": FlagDef("yellow", (
        "mature for age", "age is just a number", "don't let age stop us",
        "age doesn't matter when",
    ), "Worth examining power dynamics and shared life-stage compatibility."),
    "victim_narrative": FlagDef("yellow", (
        "my ex was crazy", "all my exes were", "everyone always leaves me",
        "i'm always the one who gets hurt", "nobody understands me",
        "people always take advantage",
    ), "Consistent external blame can indicate low accountability."),
    "trauma_dumping_early": FlagDef("yellow", (
        "abused", "assault", "mental breakdown", "self-harm", "suicidal",
        "my therapist says", "my medication", "worst year of my life",
    ), "Early trauma disclosure may signal poor boundaries or sympathy-seeking."),
    "inconsistency_hot_cold": FlagDef("yellow", (
        "mixed signals", "hot and cold", "push and pull", "disappeared for days",
        "came back out of nowhere", "one minute they", "then suddenly ignored",
    ), "Intermittent reinforcement creates anxiety - investigate before proceeding."),
    "rushed_intimacy": FlagDef("yellow", (
        "move in together", "already in love", "met last week",
        "only known a month", "know it's quick but",
    ), "Rapid escalation may be genuine or pressure - worth slowing down."),
    "financial_pressure": FlagDef("yellow", (
        "going through a rough patch", "between jobs", "just need a little",
        "invest together", "business opportunity", "loan me",
        "help me out financially", "wire transfer",
    ), "Early financial disclosures or requests warrant caution."),
    "dismissive_contempt": FlagDef("yellow", (
        "you wouldn't understand", "you're naive", "that's a dumb question",
        "obviously you don't", "should've known better", "educate yourself",
    ), "Contempt - even subtle - erodes respect over time."),
    "negative_ex_fixation": FlagDef("yellow", (
        "she was insane", "he was abusive", "never got over",
        "still dealing with my ex", "they destroyed me", "i trusted them and",
    ), "Excessive ex-focus may signal unresolved attachment or bitterness."),
}


def scan_red_flags(profile) -> tuple:
    """Returns (red_flags, yellow_flags) lists of flag category names."""
    text = (getattr(profile, "bio", "") + " " + getattr(profile, "raw_text", "")).lower()
    red_flags, yellow_flags = [], []
    for category, flag_def in FLAG_DEFS.items():
        if any(phrase in text for phrase in flag_def.phrases):
            if flag_def.severity == "red":
                red_flags.append(category)
            else:
                yellow_flags.append(category)
    return red_flags, yellow_flags


def get_flag_explanation(category: str) -> str:
    fd = FLAG_DEFS.get(category)
    return fd.explanation if fd else ""


def get_flag_severity(category: str) -> str:
    fd = FLAG_DEFS.get(category)
    return fd.severity if fd else "yellow"
