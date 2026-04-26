# b17: 7922L
import logging

import praw

import config

log = logging.getLogger(__name__)

_BLANK_CONTENT = "_No entries this week._"
_POST_TITLE = "Weekly Mod Digest"


def run(reddit: praw.Reddit) -> None:
    """Read the mod-digest wiki page and post its contents as a weekly mod post.

    If the wiki page is empty (or contains only the blank placeholder), do nothing.
    After a successful post the wiki page is reset to the blank placeholder so
    next week starts with a clean slate.  The wiki's built-in revision history
    preserves the full audit trail.
    """
    subreddit = reddit.subreddit(config.SUBREDDIT)

    try:
        wiki_page = subreddit.wiki[config.MOD_DIGEST_WIKI_PAGE]
        content = wiki_page.content_md.strip()
    except Exception as exc:
        log.error("mod_digest: could not read wiki page '%s': %s", config.MOD_DIGEST_WIKI_PAGE, exc)
        return

    if not content or content == _BLANK_CONTENT:
        log.info("mod_digest: wiki page empty — skipping this week")
        return

    try:
        submission = subreddit.submit(
            title=_POST_TITLE,
            selftext=content,
        )
    except Exception as exc:
        log.error("mod_digest: failed to submit post: %s", exc)
        return

    log.info("mod_digest: submitted post %s", submission.id)

    try:
        submission.mod.distinguish(how="yes")
        submission.mod.sticky(state=True)
        if config.MOD_DIGEST_FLAIR_ID:
            submission.mod.flair(
                text=config.MOD_DIGEST_FLAIR_TEXT,
                flair_template_id=config.MOD_DIGEST_FLAIR_ID,
            )
        elif config.MOD_DIGEST_FLAIR_TEXT:
            submission.mod.flair(text=config.MOD_DIGEST_FLAIR_TEXT)
    except Exception as exc:
        log.error("mod_digest: post submitted but post-processing failed: %s", exc)

    try:
        wiki_page.edit(
            content=_BLANK_CONTENT,
            reason="bot: cleared after weekly digest post",
        )
        log.info("mod_digest: wiki page reset for next week")
    except Exception as exc:
        log.error("mod_digest: could not reset wiki page: %s", exc)
