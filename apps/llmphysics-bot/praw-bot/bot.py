# b17: 7922L
import logging
import time

import praw
from apscheduler.schedulers.background import BackgroundScheduler
from praw.exceptions import RedditAPIException

import config
from plugins.physics_define import lookup
from plugins.mod_digest import run as run_mod_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def make_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        username=config.REDDIT_USERNAME,
        password=config.REDDIT_PASSWORD,
        user_agent=config.REDDIT_USER_AGENT,
    )


def _already_replied(comment: praw.models.Comment, me: str) -> bool:
    """Check whether the bot has already replied to this comment."""
    comment.refresh()
    for reply in comment.replies:
        if reply.author and reply.author.name == me:
            return True
    return False


def handle_comment(comment: praw.models.Comment, me: str) -> None:
    body = comment.body.strip()
    if not body.lower().startswith(config.COMMAND_PREFIX):
        return

    term = body[len(config.COMMAND_PREFIX):].strip()
    if not term:
        return

    if _already_replied(comment, me):
        log.info("Already replied to %s — skipping", comment.id)
        return

    log.info("Defining: %s (comment %s)", term, comment.id)
    reply = lookup(term, sentences=config.WIKI_SUMMARY_SENTENCES)

    footer = (
        "\n\n---\n"
        "^(I'm a bot for r/LLMPhysics. "
        "Use `!define <term>` to look up a physics concept.)"
    )
    comment.reply(reply + footer)
    log.info("Replied to %s", comment.id)


def run() -> None:
    reddit = make_reddit()
    me = reddit.user.me().name
    subreddit = reddit.subreddit(config.SUBREDDIT)
    log.info("Watching r/%s for '%s' commands...", config.SUBREDDIT, config.COMMAND_PREFIX)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: run_mod_digest(reddit),
        trigger="cron",
        day_of_week=config.MOD_DIGEST_POST_DAY,
        hour=config.MOD_DIGEST_POST_HOUR,
        minute=0,
        id="mod_digest",
    )
    scheduler.start()
    log.info(
        "mod_digest scheduled: day_of_week=%s hour=%s UTC",
        config.MOD_DIGEST_POST_DAY,
        config.MOD_DIGEST_POST_HOUR,
    )

    try:
        while True:
            try:
                for comment in subreddit.stream.comments(skip_existing=True):
                    handle_comment(comment, me)
            except (RedditAPIException, OSError) as exc:
                log.error("Stream error: %s — restarting in 60s", exc)
                time.sleep(60)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    run()
