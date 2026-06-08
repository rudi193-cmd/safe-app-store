# Privacy Policy

_Last updated: April 12, 2026_

This policy describes what data the **llmphysics-bot** Devvit app (the "Bot") reads, stores, and transmits. The Bot is open-source; you can verify everything described here against the source code in the [safe-app-llmphysics-bot](https://github.com/rudi193-cmd/safe-app-llmphysics-bot) repository.

## Summary

- The Bot does **not** collect, store, sell, or share any personal data.
- The Bot does **not** track users, build profiles, or retain a history of `!define` requests.
- The Bot reads comment text only to check whether it starts with `!define` and to extract the term that follows.
- The only persistent storage the Bot uses is a short-lived cache of its own configuration.

## 1. What the Bot reads

The Bot processes the following on the subreddits where it is installed:

**Comments.** When a new comment is submitted, Devvit delivers a `CommentSubmit` event to the Bot. The Bot examines the comment body only to:

1. Check whether it starts with the prefix `!define`.
2. If it does, extract the term after the prefix so it can be looked up on Wikipedia.

Comments that do not start with `!define` are ignored and are not read or retained in any way.

**Wiki pages.** The Bot reads two wiki pages on the subreddit where it is installed:

- `mod/llmphysics-bot/config` — the mod-only runtime configuration page.
- `mod-digest` (or whatever name the config specifies) — read once per week and reposted as a moderator post, then reset.

**Wikipedia.** For each `!define` request, the Bot issues an HTTPS request to `https://en.wikipedia.org` to fetch the article summary and categories for the requested term. Wikipedia may log those requests according to [its own privacy policy](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy). The Bot does not send Wikipedia any information about the Reddit user who issued the command — only the term itself.

## 2. What the Bot stores

The Bot uses Reddit's Devvit-hosted Redis store for a small amount of operational state:

| Key | Contents | Purpose | Retention |
|---|---|---|---|
| `bot:config` | JSON-serialized copy of the current config YAML | Avoid re-fetching the wiki page on every command | 60 seconds (auto-expired) |
| `bot:digest:jobId` | Scheduler job ID of the weekly digest job | Allow the job to be cancelled and rescheduled when the cron changes | Until the next reschedule |
| `bot:digest:cron` | The cron string currently in use | Detect when the config cron has changed | Until the next reschedule |

The Bot does **not** store:

- Comment bodies, comment IDs, or any record of `!define` requests.
- Usernames, user IDs, or any information about the users who invoke the command.
- Wikipedia API responses.
- IP addresses, device information, or any telemetry.
- Any analytics of any kind.

## 3. What the Bot posts

The Bot posts two kinds of content on subreddits where it is installed:

1. **Reply comments** to `!define` commands, containing a short Wikipedia excerpt and a link to the source article. These are public Reddit comments authored by the account the moderators installed the app under.
2. **Weekly mod digest posts**, containing the verbatim contents of the `mod-digest` wiki page, posted by the same account and stickied by moderator action.

These posts are public Reddit content and are subject to Reddit's own data handling.

## 4. Third parties

The Bot communicates with exactly one third-party service: **the English Wikipedia** (`en.wikipedia.org`). No other external services are contacted.

The Bot does **not** use analytics providers, advertising networks, crash reporting, or any other third-party SDKs.

## 5. Data on the Devvit platform

The Bot runs on Reddit's Devvit platform. Reddit handles the infrastructure, authentication, and event delivery. Reddit's own data practices — including how Reddit handles the comment and wiki events it delivers to the Bot — are governed by the [Reddit Privacy Policy](https://www.reddit.com/policies/privacy-policy) and the [Devvit Terms](https://developers.reddit.com/docs/guidelines).

## 6. Children's privacy

The Bot does not knowingly collect any data from anyone, including children. Reddit itself requires users to be at least 13 years old (and older in some jurisdictions).

## 7. Your rights

Because the Bot does not store personal data, there is no user data for it to export, rectify, or delete. If you would like the Bot to stop replying to your comments, you can simply stop using the `!define` command. Moderators of a subreddit where the Bot is installed can uninstall it at any time using `devvit uninstall` or through the subreddit's app settings.

If you believe the Bot has posted a reply that violates your rights (for example, as part of a harassment situation), please contact the subreddit's moderators or file a takedown request as a GitHub issue (see below).

## 8. Changes

This policy may be updated from time to time. Updates will be committed to the repository. The "Last updated" date at the top of this document reflects the most recent change. Material changes will be noted in the commit message.

## 9. Contact

Questions about this policy, or requests related to it, should be filed as an issue on the [GitHub repository](https://github.com/rudi193-cmd/safe-app-llmphysics-bot/issues).
