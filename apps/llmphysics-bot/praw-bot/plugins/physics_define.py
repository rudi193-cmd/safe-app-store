# b17: 7922L
import wikipediaapi

import config

wiki = wikipediaapi.Wikipedia(
    language=config.WIKIPEDIA_LANG,
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent=config.REDDIT_USER_AGENT,
)


def lookup(term: str, sentences: int = 3) -> str:
    """Return a short Wikipedia summary for a physics term."""
    page = wiki.page(term)

    if not page.exists():
        return f'No Wikipedia article found for "{term}".'

    summary = ". ".join(page.summary.split(". ")[:sentences])
    if not summary.endswith("."):
        summary += "."

    return f"**{page.title}**\n\n{summary}\n\n[Read more]({page.fullurl})"
