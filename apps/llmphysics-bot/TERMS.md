# Terms and Conditions

_Last updated: April 12, 2026_

These terms govern your use of the **llmphysics-bot** Devvit app (the "Bot"), which is open-source software maintained in the [safe-app-llmphysics-bot](https://github.com/rudi193-cmd/safe-app-llmphysics-bot) repository.

## 1. What the Bot does

The Bot is a Reddit Devvit app that:

- Replies to public comments beginning with `!define <term>` with a short summary from the English Wikipedia.
- Reads a subreddit wiki page named `mod-digest` on a weekly schedule, posts its contents as a moderator post, and resets the page.
- Reads a mod-only wiki page named `mod/llmphysics-bot/config` to load its runtime configuration.

## 2. Acceptance

By installing the Bot on a subreddit, or by interacting with the Bot in a subreddit where it is installed, you agree to these Terms. If you do not agree, do not install the Bot and do not use the `!define` command.

## 3. Reddit's rules apply

The Bot runs on Reddit's Devvit platform. Your use of the Bot is also subject to:

- [Reddit's User Agreement](https://www.redditinc.com/policies/user-agreement)
- [Reddit's Content Policy](https://www.redditinc.com/policies/content-policy)
- [Reddit's Developer Terms](https://www.redditinc.com/policies/developer-terms)

Nothing in these Terms overrides Reddit's own rules.

## 4. Moderator responsibility

Moderators who install the Bot on a subreddit are responsible for:

- The contents of the `mod/llmphysics-bot/config` wiki page and any settings they configure there.
- The contents of the `mod-digest` wiki page, which the Bot will post verbatim as a moderator post.
- Ensuring the Bot's behavior on their subreddit complies with Reddit's rules and applicable law.

The Bot posts replies using the authority of the account that installed it. Moderators are responsible for those posts in the same way they are responsible for any other automated tool they choose to run on their subreddit.

## 5. User conduct

When using the `!define` command, you agree not to:

- Use the Bot to harass, defame, or impersonate anyone.
- Attempt to use the Bot to fetch content that violates Wikipedia's terms of use or Reddit's Content Policy.
- Attempt to disrupt, overload, or reverse-engineer the Bot or the Devvit platform.

## 6. Third-party content

The Bot fetches summaries from the **English Wikipedia** via the public Wikipedia REST and MediaWiki APIs. Wikipedia content is authored by third parties and is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The Bot reproduces short excerpts and links back to the source article. The maintainers of the Bot do not endorse, verify, or take responsibility for the accuracy of Wikipedia content.

## 7. No warranty

The Bot is provided **"as is"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. The maintainers do not guarantee that the Bot will be available, accurate, or free of errors.

## 8. Limitation of liability

To the maximum extent permitted by applicable law, in no event shall the maintainers or copyright holders of the Bot be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the Bot or its use.

## 9. License

The source code of the Bot is licensed under the [MIT License](LICENSE). These Terms do not restrict your rights under that license with respect to the source code.

## 10. Changes

These Terms may be updated from time to time. Updates will be committed to the repository. Continued use of the Bot after an update constitutes acceptance of the revised Terms. The "Last updated" date at the top of this document reflects the most recent change.

## 11. Contact

Questions, complaints, or takedown requests should be filed as an issue on the [GitHub repository](https://github.com/rudi193-cmd/safe-app-llmphysics-bot/issues).
