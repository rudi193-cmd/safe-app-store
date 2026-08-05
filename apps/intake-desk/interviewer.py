"""The interviewer socket.

The finding this app is built on: a persona is not a skin, it is an
elicitation protocol. Nobody fills in a form about their dead friend; people
answer Riggs. So the desk ships the socket, and the character is injected.

Three session rules are enforced here rather than written into a profile,
because a profile that can waive them is not a rule:

  1. The consent scope is read aloud, in plain language, before the first
     question. `open_session` refuses to start otherwise.
  2. The interviewer never corrects the narrator mid-session.
  3. The domain's principles travel with the profile into whatever renders it.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import consent as consent_mod

PROFILE_DIR = Path(__file__).with_name("interviewers")

CONSENT_SCRIPT = (
    "Before we start: what you tell me gets written down and kept on this "
    "machine, under the name you give me. It does not leave here unless you "
    "say it can, separately. You can change your mind at any time and I will "
    "stop using it — the record of your saying so stays too. Is that all right?"
)


class InterviewerError(Exception):
    pass


@dataclass(frozen=True)
class Interviewer:
    name: str
    full_name: str
    domain: str
    voice: str
    principles: tuple[str, ...]
    openers: tuple[str, ...]
    follow_ups: tuple[str, ...]
    refusals: tuple[str, ...]

    def brief(self) -> str:
        """The profile, rendered for whatever conducts the session.

        Deliberately plain text: this is handed to a model when one is
        available, and read by a human taker when one is not.
        """
        lines = [
            f"You are {self.full_name}. You are conducting an intake for: {self.domain}.",
            "",
            "VOICE:", self.voice.strip(), "",
            "PRINCIPLES — these change what gets recorded, so follow them exactly:",
        ]
        lines += [f"  - {p}" for p in self.principles]
        lines += ["", "HOW YOU ASK:"]
        lines += [f"  - {f}" for f in self.follow_ups]
        lines += ["", "YOU DO NOT:"]
        lines += [f"  - {r}" for r in self.refusals]
        return "\n".join(lines)


def load(name: str = "riggs", *, profile_dir: Path | None = None) -> Interviewer:
    """Load an injected interviewer profile by name."""
    path = (profile_dir or PROFILE_DIR) / f"{name}.toml"
    if not path.exists():
        raise InterviewerError(f"no interviewer profile: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    missing = {"name", "voice", "principles", "refusals"} - data.keys()
    if missing:
        raise InterviewerError(f"{path.name} is missing: {', '.join(sorted(missing))}")
    return Interviewer(
        name=data["name"],
        full_name=data.get("full_name", data["name"]),
        domain=data.get("domain", ""),
        voice=data["voice"],
        principles=tuple(data["principles"]),
        openers=tuple(data.get("openers", ())),
        follow_ups=tuple(data.get("follow_ups", ())),
        refusals=tuple(data["refusals"]),
    )


def available(profile_dir: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (profile_dir or PROFILE_DIR).glob("*.toml"))


def open_session(
    *,
    consent_store,
    narrator_id: str,
    interviewer: Interviewer,
) -> str:
    """Begin an intake, or refuse.

    Session rule 1: the scope is read aloud and the record exists before the
    first question. This is the enforcement, not the profile's good manners.
    """
    if not consent_mod.may_keep(consent_store, narrator_id):
        raise InterviewerError(
            "no verified keeping consent — read the scope aloud and record the "
            f"grant before opening a session:\n\n{CONSENT_SCRIPT}"
        )
    opener = interviewer.openers[0] if interviewer.openers else "Tell me about it."
    return opener
