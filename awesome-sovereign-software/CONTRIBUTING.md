# Contributing

Thanks for helping keep this list useful. The bar is the [Sovereignty Test](README.md#the-sovereignty-test) —
read it before opening a pull request.

## Ground rules

- **One app per pull request.** Small PRs get reviewed fast; batches stall.
- **Fill in the checklist** in the PR template. Every criterion, honestly. "Mostly" is a no.
- **Alphabetical order** within each category.
- **No self-promotion without disclosure.** Submitting your own project is welcome — say so in
  the PR, and it will be marked in the entry like the existing disclosed entries.
- Removals and corrections are as valuable as additions. If an app added an account wall,
  went subscription-only, or shut down, open a PR (or an issue) to **delist** it — entries move
  to the Delisted section with a date and reason, they don't silently vanish. A delisted app
  can return by reversing the regression.

## Entry format

```markdown
- [Name](https://homepage-or-repo) `LICENSE` <badges> — One sentence: what it does and why it is sovereign.
  - *Exit: how you leave with your data, in one sentence.*
```

- Link to the project homepage, or the source repository if there is no homepage.
- `LICENSE` in backticks: the SPDX identifier (`MIT`, `AGPL-3.0`, …), `Source-available`, or `Proprietary`.
- Badges, in this order where they apply: 📄 plain-file data · 🗃️ open database format · 📵 fully offline · 🔁 optional user-controlled/E2EE sync.
- Description ends with a period. Keep it under ~25 words. Say what the data story is if it isn't obvious.
- **The exit line is mandatory.** Name the concrete mechanism — the file format, the export
  command, the folder you copy. "It has export" is not an exit plan; "export decks as `.apkg`
  or plain text" is. If you can't write the line honestly, the app doesn't qualify.

## What gets rejected

- Requires an account, sign-up, or activation for core features.
- Requires a server — including "just self-host it." Those belong on
  [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted).
- Core functionality behind a subscription or that stops working when payment stops.
- Data locked in an undocumented format with no real export.
- Phones home as a condition of working (license checks that brick the app offline count).
- Abandoned **and** broken. Abandoned but still working is fine — that's rather the point —
  but note it in the PR so it can be flagged if needed.

## Proprietary software

Admitted reluctantly, and only when the data format is fully open (e.g. a folder of Markdown)
and every other criterion passes. Always marked `Proprietary`. When an open-source app does the
same job as well, it is preferred and the proprietary one may be dropped.

## New categories

Open an issue first. A category needs at least three qualifying entries to exist.
