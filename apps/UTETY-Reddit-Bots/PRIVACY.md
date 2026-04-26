# Privacy Policy

_Last updated: April 15, 2026_

This policy describes what data the **UTETY Reddit Bots** Devvit apps (the "Bots") read, store, and transmit. The Bots are open-source; you can verify everything described here against the source code in the [safe-app-UTETY-Reddit-Bots](https://github.com/rudi193-cmd/safe-app-UTETY-Reddit-Bots) repository.

## Summary

- The Bots do **not** collect, store, sell, or share any personal data.
- The Bots do **not** track users, build profiles, or retain a history of posts witnessed.
- The Bots read post and comment content only to determine whether a witnessing threshold has been crossed.
- The only persistent storage the Bots use is operational state (rate limit counters, witnessed post flags) stored in Reddit's Devvit-hosted Redis.

## 1. What the Bots read

**Posts.** When a new post is submitted, Devvit delivers a `PostSubmit` event. The Bots examine the post body to detect specific textual patterns (paper-shape heuristics, epistemic confidence markers). Posts that do not match are not retained in any way.

**Post scores.** The Bots poll recent post scores on a scheduled interval to detect when a post crosses a karma threshold. Only the numeric score is evaluated — no post content is read or stored during this check.

The Bots do **not** read private messages, user profiles, or any content outside of the subreddits where they are installed.

## 2. What the Bots store

The Bots use Reddit's Devvit-hosted Redis store for operational state only:

| Key pattern | Contents | Purpose | Retention |
|---|---|---|---|
| `gerald:ratelimit:<sub>:<date>` | Integer count | Per-subreddit daily appearance cap | 48 hours (auto-expired) |
| `gerald:witnessed:<postId>` | Flag | Prevent witnessing the same post twice | 30 days (auto-expired) |
| `gerald:cooldown:<author>:<trigger>` | Flag | Per-author per-trigger cooldown | Per trigger config (default 24h) |

The Bots do **not** store:
- Post bodies, comment bodies, or any text content.
- Usernames, user IDs, or any information about authors beyond the cooldown flag keyed to their username.
- IP addresses, device information, or any telemetry.
- Any analytics of any kind.

## 3. What the Bots post

The Bots post single-word or single-emoji comments on posts in the subreddits where they are installed. These are public Reddit comments subject to Reddit's own data handling.

## 4. Third parties

The UTETY Bots do **not** communicate with any third-party services. There is no external HTTP egress.

## 5. Data on the Devvit platform

The Bots run on Reddit's Devvit platform. Reddit handles infrastructure, authentication, and event delivery. Reddit's own data practices are governed by the [Reddit Privacy Policy](https://www.reddit.com/policies/privacy-policy) and the [Devvit Terms](https://developers.reddit.com/docs/guidelines).

## 6. Children's privacy

The Bots do not knowingly collect any data from anyone. Reddit requires users to be at least 13 years old.

## 7. Your rights

Because the Bots do not store personal data beyond rate limit counters (which auto-expire), there is no user data to export or delete. Moderators can uninstall a Bot at any time through the subreddit's app settings.

## 8. Changes

This policy may be updated from time to time. Updates will be committed to the repository. The "Last updated" date at the top reflects the most recent change.

## 9. Contact

Questions should be filed as an issue on the [GitHub repository](https://github.com/rudi193-cmd/safe-app-UTETY-Reddit-Bots/issues).
