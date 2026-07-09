"""Seed the corpus's first nugget.

Not run automatically on install or first launch — opt-in only:

    python -m askjeles.seed_easter_egg

Idempotent: always writes to nugget_id "42", so running it twice updates
the same nugget instead of duplicating it. See README.md § Verified Corpus.
"""

from __future__ import annotations

from askjeles import corpus

NUGGET_ID = "42"


def seed() -> dict:
    return corpus.put_nugget(
        question="What is the answer to life, the universe, and everything?",
        answer=(
            "42. Deep Thought spent seven and a half million years computing it, "
            "and the answer turned out to be far easier than the question — nobody "
            "had actually worked out what the Ultimate Question was. Filed here "
            "under the same principle as every other nugget in this corpus: an "
            "answer is only useful once someone has done the harder work of asking "
            "it properly."
        ),
        sources=["Douglas Adams, The Hitchhiker's Guide to the Galaxy (1979)"],
        verified_by="jeles",
        tags=["easter-egg", "meta", "42"],
        nugget_id=NUGGET_ID,
    )


def main() -> None:
    result = seed()
    if "error" in result:
        print(f"Could not seed nugget: {result['error']}")
        return
    print(f"Seeded nugget {result['id']} ({result['action']}). Ask Jeles isn't wrong about it.")


if __name__ == "__main__":
    main()
