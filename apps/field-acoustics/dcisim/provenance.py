"""Where each number in the model came from.

The audits made the case for this file. The propagation core was verified
correct to 1e-14 dB against independent reimplementations, and the results were
still wrong -- because a directivity floor was asserted rather than measured,
because a snare carry angle was guessed at 45 degrees when the real one is near
80, because a bass line was placed off centre and its asymmetry got read as a
finding. Correct code over unverified inputs produces confident, wrong answers.

So every input carries its state, and results carry the weakest state they
depend on:

    MEASURED   from a published dataset, with a citation someone can check
    FITTED     an analytic model calibrated against published values
    ASSUMED    asserted by the author; nothing has verified it

This is deliberately not a confidence score. A number is not 0.7 verified. It
either traces to something a person can look up, or it does not, and blurring
that into a percentage is how "the model says 5.2 dB" ends up in a room full of
caption heads with nothing behind it.

The rule that makes it useful: a result is only as verified as its weakest
input. One ASSUMED term anywhere in the chain and the whole answer is ASSUMED,
however many MEASURED terms sit beside it.
"""

from dataclasses import dataclass, field
from enum import IntEnum


class State(IntEnum):
    """Ordered worst-to-best so `min()` propagates the weakest input."""

    ASSUMED = 0
    FITTED = 1
    MEASURED = 2

    @property
    def mark(self):
        return {State.MEASURED: "*", State.FITTED: "~", State.ASSUMED: "!"}[self]

    @property
    def label(self):
        return self.name.lower()


@dataclass(frozen=True)
class Source:
    """Provenance of one model input."""

    state: State
    what: str  # the quantity, e.g. "trumpet directivity"
    citation: str = ""  # where it came from, if anywhere
    note: str = ""

    def __str__(self):
        bits = "%s %-9s %s" % (self.state.mark, self.state.label, self.what)
        if self.citation:
            bits += "  [%s]" % self.citation
        return bits


@dataclass
class Provenance:
    """A collection of inputs, reporting the weakest state among them."""

    sources: list = field(default_factory=list)

    def add(self, state, what, citation="", note=""):
        self.sources.append(Source(state, what, citation, note))
        return self

    def extend(self, other):
        self.sources.extend(other.sources)
        return self

    @property
    def state(self):
        """The weakest state present -- what the whole result is worth."""
        return min((s.state for s in self.sources), default=State.ASSUMED)

    def weakest(self):
        """Every input at the limiting state. These are what to fix first."""
        worst = self.state
        return [s for s in self.sources if s.state is worst]

    def report(self):
        lines = ["Inputs, worst first:"]
        for s in sorted(self.sources, key=lambda s: (s.state, s.what)):
            lines.append("  " + str(s))
        lines.append("")
        lines.append("This result is %s -- no stronger than its weakest input."
                     % self.state.label.upper())
        limiting = self.weakest()
        if limiting and self.state is not State.MEASURED:
            lines.append("Limited by: " + ", ".join(sorted(s.what for s in limiting)))
        return "\n".join(lines)


# ── Citations for the model's current inputs ────────────────────────────────

ISO_9613_1 = "ISO 9613-1:1993, atmospheric absorption"
IEC_61672 = "IEC 61672, A-weighting"
MEYER_BRASS = "Meyer, Acoustics and the Performance of Music, brass directivity indices"

# Datasets this model can consume but does not ship. BYU's repository defaults
# to CC BY 4.0 (attribution only), which is compatible with this project's
# Apache-2.0 licence. The TU Berlin database is CC BY-NC-SA -- the
# non-commercial term makes it unusable here and restrictive for downstream
# users, so it is deliberately not supported as a bundled source.
BYU_DIRECTIVITY = ("Bellows et al., BYU Spatial Audio Library, "
                   "scholarsarchive.byu.edu/directivity (CC BY 4.0)")


def model_provenance(instruments=None):
    """Provenance for everything a simulation result depends on.

    Call this before quoting a number at anyone. It is the honest answer to
    "where did that come from", and it names the inputs holding the result back.
    """
    from .instruments import CATALOG

    p = Provenance()
    names = sorted(CATALOG) if instruments is None else sorted(instruments)

    p.add(State.MEASURED, "atmospheric absorption", ISO_9613_1,
          "verified against published tables to under 1.5% in every band")
    p.add(State.MEASURED, "A-weighting", IEC_61672)

    for name in names:
        inst = CATALOG.get(name)
        if inst is not None:
            p.sources.append(inst.provenance())

    p.add(State.ASSUMED, "rear front-to-back ratios",
          note="asserted per band in directivity.py. Turning a form inward puts "
               "most of the hornline behind 90 degrees, so this is the single "
               "most load-bearing input in the model")
    p.add(State.ASSUMED, "instrument sound powers",
          note="calibrated so a full corps lands near published stadium levels, "
               "but not measured from any real ensemble")
    p.add(State.ASSUMED, "battery carry angles",
          note="snare ~80 and tenor ~72 degrees from observation, not measurement; "
               "worth about 0.6 dB on the headline")
    p.add(State.ASSUMED, "grandstand absorption",
          note="occupied-seating values from general acoustics practice, not from "
               "any surveyed venue")
    p.add(State.FITTED, "propagation geometry",
          note="spherical spreading and an image-source reflection; verified "
               "against independent reimplementations to 1e-14 dB")
    return p
