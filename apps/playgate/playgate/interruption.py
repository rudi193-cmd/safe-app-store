"""Interruption as a recorded fact with a provenance state.

The fact this module carries is deliberately narrow: how many times, in ten
minutes of ordinary play, an application stops the child to show them something
they did not ask for. Not "is this app ok". Not a score. A count, plus the
things that make a count usable.

Three provenance states and nothing else:

    assumed   nobody has looked
    fitted    derived from something adjacent (ad SDKs present, the publisher's
              other titles) by a stated rule
    measured  a person watched it run and counted

`assumed` is the default and it is a *value*. An app nobody has checked and an
app measured at zero interruptions are opposite facts; a catalog that renders
them the same way — a blank cell, a missing badge — has started lying without
anyone deciding to. So a missing record is an error here, not an empty string.

The demotion rule in `effective()` is the part that has to be automatic. An
interruption count measures a *build*: ad load is a tuning parameter product
teams adjust continuously, so a count observed on 3.1 says nothing about 3.2. A
measurement that does not decay when its subject changes underneath it is worse
than no measurement, because it carries the authority of having been checked
while describing a build that no longer exists.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

#: Weakest to strongest. `weakest()` and the ordering comparisons below are the
#: only places this sequence should be encoded.
PROVENANCE_ORDER = ("assumed", "fitted", "measured")

VALID_PROVENANCE = frozenset(PROVENANCE_ORDER)

#: How the interruption ends. `deceptive_close` is not a worse `unskippable` —
#: it is a different mechanism, in which the attempt to escape the interruption
#: is itself monetised. A parent told "one ad every five minutes" and not told
#: this has not been told the important part.
VALID_DISMISSAL = frozenset({
    "immediate", "after_delay", "unskippable", "deceptive_close",
})


class InterruptionError(ValueError):
    """A record that cannot be trusted to mean what it says."""


@dataclass(frozen=True)
class Interruption:
    """One app's interruption record, as observed at one moment on one build."""

    provenance: str
    count_per_10min: int | None = None
    dismissal: str | None = None
    observed_version: str | None = None
    observed_at: str | None = None          # ISO date
    observed_by: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.provenance not in VALID_PROVENANCE:
            raise InterruptionError(
                f"provenance {self.provenance!r} not one of {sorted(VALID_PROVENANCE)}"
            )
        if self.dismissal is not None and self.dismissal not in VALID_DISMISSAL:
            raise InterruptionError(f"dismissal {self.dismissal!r} not recognised")

        if self.provenance == "assumed":
            # An assumed record that carries a count is a guess wearing an
            # observation's clothes. There is nowhere for the number to have
            # come from.
            if self.count_per_10min is not None:
                raise InterruptionError(
                    "assumed record carries a count; if a count exists the "
                    "state is fitted or measured"
                )
            return

        if self.count_per_10min is None:
            raise InterruptionError(f"{self.provenance} record carries no count")
        if self.count_per_10min < 0:
            raise InterruptionError("count_per_10min is negative")

        if self.provenance == "fitted" and not self.note:
            # `fitted` means "derived by a stated rule". An unstated rule is
            # not a rule, and the number would be unauditable.
            raise InterruptionError("fitted record must state the rule in note")

        if self.provenance == "measured":
            missing = [
                name for name in ("observed_version", "observed_at", "observed_by")
                if not getattr(self, name)
            ]
            if missing:
                raise InterruptionError(
                    f"measured record missing {missing}; a measurement that is "
                    "not bound to a build and a date cannot be demoted when the "
                    "build changes"
                )

    # -- reading -----------------------------------------------------------

    def effective(self, installed_version: str | None) -> "Interruption":
        """This record as it applies to `installed_version`.

        A measured record whose observed build is not the installed build
        demotes to fitted: the old count is still evidence about how this
        publisher behaves, which is exactly what fitted means, but it is no
        longer an observation of the thing in front of the child.

        Nobody has to remember to call this — the catalog and the disposition
        log both route through it.
        """
        if self.provenance != "measured":
            return self
        if installed_version is None or installed_version == self.observed_version:
            return self
        return replace(
            self,
            provenance="fitted",
            note=(
                f"measured on {self.observed_version}, installed is "
                f"{installed_version}; demoted automatically"
            ),
        )

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_json(cls, raw: object) -> "Interruption":
        """Parse a record. A missing record is an error, not an `assumed` one.

        Defaulting silently to `assumed` here would be the whole failure this
        module exists to prevent: it would make "nobody wrote a record" and
        "somebody recorded that nobody has looked" indistinguishable, and only
        one of those is a fact.
        """
        if raw is None:
            raise InterruptionError(
                "no interruption record; write an explicit "
                '{"provenance": "assumed"} rather than omitting the field'
            )
        if not isinstance(raw, dict):
            raise InterruptionError(f"interruption record is {type(raw).__name__}, not an object")
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise InterruptionError(f"unknown interruption fields {sorted(unknown)}")
        if "provenance" not in raw:
            raise InterruptionError("interruption record has no provenance")
        return cls(**raw)


def weakest(*states: str) -> str:
    """The weakest of several provenance states.

    A view built from several facts is worth its loosest input. Not a
    percentage and not an average — averaging is the operation by which a
    strong input hides a weak one.
    """
    if not states:
        raise InterruptionError("weakest() of nothing")
    for state in states:
        if state not in VALID_PROVENANCE:
            raise InterruptionError(f"provenance {state!r} not recognised")
    return min(states, key=PROVENANCE_ORDER.index)


UNCHECKED = Interruption(provenance="assumed", note="nobody has watched this run")
