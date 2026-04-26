import { Devvit, Context } from '@devvit/public-api';
import { load as parseYaml } from 'js-yaml';

Devvit.configure({
  redditAPI: true,
  http: true,
  redis: true,
});

const COMMAND = '!define';
const CONFIG_WIKI_PAGE = 'mod/llmphysics-bot/config';
const DIGEST_JOB = 'mod_digest';
const HEARTBEAT_JOB = 'config_heartbeat';
const HEARTBEAT_CRON = '*/5 * * * *';
const BLANK_DIGEST = '_No entries this week._';

// Redis keys
const CONFIG_CACHE_KEY = 'bot:config';
const CONFIG_CACHE_SECONDS = 60;
const DIGEST_JOB_ID_KEY = 'bot:digest:jobId';
const DIGEST_CRON_KEY = 'bot:digest:cron';
const HEARTBEAT_JOB_ID_KEY = 'bot:heartbeat:jobId';

// ---------------------------------------------------------------------------
// Config schema + defaults
// ---------------------------------------------------------------------------
interface BotConfig {
  bot_username: string;
  allowed_category_keywords: string[];
  blocked_terms: string[];
  mod_digest: {
    wiki_page: string;
    cron: string;
    post_title: string;
  };
  reply: {
    summary_sentences: number;
    footer: string;
    not_found_message: string;
    off_topic_message: string;
    error_message: string;
  };
}

const DEFAULT_CONFIG: BotConfig = {
  bot_username: 'llmphysics-bot',
  allowed_category_keywords: [
    'physics',
    'mathematics',
    'chemistry',
    'astronomy',
    'astrophysics',
    'quantum',
    'relativity',
    'mechanics',
    'thermodynamics',
    'cosmology',
    'particle',
    'science',
  ],
  blocked_terms: [],
  mod_digest: {
    wiki_page: 'mod-digest',
    cron: '0 0 * * 0',
    post_title: 'Weekly Mod Digest',
  },
  reply: {
    summary_sentences: 3,
    footer:
      "^(I'm a bot for r/LLMPhysics. Use `!define <term>` to look up a physics concept.)",
    not_found_message: 'No Wikipedia article found for "{term}".',
    off_topic_message:
      'Sorry, "{term}" doesn\'t look like a science topic I cover.',
    error_message:
      "Sorry, I couldn't reach Wikipedia right now. Try again in a moment.",
  },
};

function mergeConfig(base: BotConfig, over: Partial<BotConfig>): BotConfig {
  return {
    bot_username: (over.bot_username ?? base.bot_username).toLowerCase(),
    allowed_category_keywords:
      over.allowed_category_keywords ?? base.allowed_category_keywords,
    blocked_terms: (over.blocked_terms ?? base.blocked_terms).map((t) =>
      String(t).toLowerCase(),
    ),
    mod_digest: { ...base.mod_digest, ...(over.mod_digest ?? {}) },
    reply: { ...base.reply, ...(over.reply ?? {}) },
  };
}

// Reddit wiki pages render markdown in the browser, which turns YAML `#`
// comments into giant headers. Mods are expected to wrap the YAML in a
// ```yaml ... ``` fenced code block for clean rendering. This strips that
// fence before parsing so both fenced and unfenced configs work.
function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:ya?ml)?\s*\n([\s\S]*?)\n```$/i);
  return fenced ? fenced[1] : trimmed;
}

// ---------------------------------------------------------------------------
// Config loading (Redis cache, 60s TTL)
// ---------------------------------------------------------------------------
async function loadConfig(
  context: Context,
  opts: { bypassCache?: boolean } = {},
): Promise<BotConfig> {
  if (!opts.bypassCache) {
    const cached = await context.redis.get(CONFIG_CACHE_KEY);
    if (cached) {
      try {
        return JSON.parse(cached) as BotConfig;
      } catch (e) {
        console.warn(`config: cached value unparseable (${e}), reloading`);
      }
    }
  }

  const subreddit = await context.reddit.getCurrentSubreddit();
  let config = DEFAULT_CONFIG;
  let source = 'defaults';

  try {
    const page = await context.reddit.getWikiPage(
      subreddit.name,
      CONFIG_WIKI_PAGE,
    );
    const raw = stripCodeFence(page.content);
    const parsed = parseYaml(raw) as Partial<BotConfig> | null;
    if (parsed && typeof parsed === 'object') {
      config = mergeConfig(DEFAULT_CONFIG, parsed);
      source = `wiki:${CONFIG_WIKI_PAGE}`;
    } else {
      console.warn(
        `config: wiki page "${CONFIG_WIKI_PAGE}" parsed to ${typeof parsed}; using defaults`,
      );
    }
  } catch (e) {
    console.log(
      `config: could not read wiki page "${CONFIG_WIKI_PAGE}" (${e}); using defaults`,
    );
  }

  console.log(
    `config loaded from ${source}: ` +
      `cron="${config.mod_digest.cron}" ` +
      `digest_page="${config.mod_digest.wiki_page}" ` +
      `bot_username="${config.bot_username}" ` +
      `allowed_keywords=${config.allowed_category_keywords.length} ` +
      `blocked_terms=${config.blocked_terms.length}`,
  );

  try {
    await context.redis.set(CONFIG_CACHE_KEY, JSON.stringify(config));
    await context.redis.expire(CONFIG_CACHE_KEY, CONFIG_CACHE_SECONDS);
  } catch (e) {
    console.warn(`config: cache write failed: ${e}`);
  }

  return config;
}

// ---------------------------------------------------------------------------
// Command parsing
// ---------------------------------------------------------------------------
interface ParsedCommand {
  term: string;
  mode: 'prefix' | 'summon';
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Extract the definition target from whatever follows `!define`.
// Stops at sentence-ending punctuation or newline. Trims stray punctuation.
function extractTerm(afterCommand: string): string | null {
  const match = afterCommand.match(/^[^\n.?]*/);
  if (!match) return null;
  const term = match[0]
    .replace(/^[\s!,;:]+/, '')
    .replace(/[\s!,;:]+$/, '')
    .trim();
  return term || null;
}

function parseCommand(body: string, config: BotConfig): ParsedCommand | null {
  const trimmed = body.trim();
  const trimmedLower = trimmed.toLowerCase();
  const commandLower = COMMAND.toLowerCase();

  // Case 1: prefix mode — comment starts with !define
  if (trimmedLower.startsWith(commandLower)) {
    const term = extractTerm(trimmed.slice(COMMAND.length));
    if (term) return { term, mode: 'prefix' };
    return null;
  }

  // Case 2: summon mode — comment mentions u/<bot> and contains !define
  const mentionPattern = new RegExp(
    `\\bu/${escapeRegex(config.bot_username)}\\b`,
    'i',
  );
  if (!mentionPattern.test(body)) return null;

  const defineIdx = body.toLowerCase().indexOf(commandLower);
  if (defineIdx === -1) return null;

  const term = extractTerm(body.slice(defineIdx + COMMAND.length));
  if (term) return { term, mode: 'summon' };
  return null;
}

// ---------------------------------------------------------------------------
// Wikipedia
// ---------------------------------------------------------------------------
interface WikiSummary {
  title: string;
  extract: string;
  content_urls: { desktop: { page: string } };
}

async function fetchSummary(term: string): Promise<WikiSummary | null> {
  const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`;
  const res = await fetch(url);
  if (!res.ok) {
    console.log(
      `wikipedia: summary lookup for "${term}" returned ${res.status}`,
    );
    return null;
  }
  return (await res.json()) as WikiSummary;
}

// Try the full extracted term first. If Wikipedia has no match and the term
// is multi-word (the user probably pasted prose after `!define`), retry with
// just the first word. This rescues cases like `!define cosmology do you
// have any evidence?` → falls back to `cosmology`.
async function lookupTerm(term: string): Promise<WikiSummary | null> {
  const direct = await fetchSummary(term);
  if (direct) return direct;

  const firstWord = term.split(/\s+/)[0] ?? '';
  if (firstWord && firstWord !== term) {
    console.log(
      `define: "${term}" not found on Wikipedia, falling back to "${firstWord}"`,
    );
    return await fetchSummary(firstWord);
  }
  return null;
}

async function fetchCategories(title: string): Promise<string[]> {
  const url =
    `https://en.wikipedia.org/w/api.php?action=query&format=json` +
    `&prop=categories&cllimit=max&clshow=!hidden` +
    `&titles=${encodeURIComponent(title)}`;
  const res = await fetch(url);
  if (!res.ok) {
    console.log(
      `wikipedia: categories lookup for "${title}" returned ${res.status}`,
    );
    return [];
  }
  const data = (await res.json()) as {
    query?: {
      pages?: Record<string, { categories?: { title: string }[] }>;
    };
  };
  const pages = data.query?.pages ? Object.values(data.query.pages) : [];
  if (pages.length === 0) return [];
  const cats = pages[0].categories ?? [];
  return cats.map((c) => c.title.replace(/^Category:/, '').toLowerCase());
}

function isAllowedTopic(categories: string[], config: BotConfig): boolean {
  if (config.allowed_category_keywords.length === 0) return true;
  const keywords = config.allowed_category_keywords.map((k) => k.toLowerCase());
  return categories.some((cat) => keywords.some((kw) => cat.includes(kw)));
}

function renderTemplate(tmpl: string, vars: Record<string, string>): string {
  return tmpl.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`);
}

function firstSentences(text: string, n: number): string {
  const parts = text.split('. ');
  const slice = parts.slice(0, Math.max(1, n)).join('. ');
  return slice.endsWith('.') ? slice : slice + '.';
}

// ---------------------------------------------------------------------------
// Scheduler management
// ---------------------------------------------------------------------------
async function ensureDigestScheduled(
  context: Context,
  config: BotConfig,
): Promise<void> {
  const desired = config.mod_digest.cron;
  const current = await context.redis.get(DIGEST_CRON_KEY);
  if (current === desired) {
    console.log(`digest: cron already in sync ("${desired}"), no reschedule`);
    return;
  }

  const existingId = await context.redis.get(DIGEST_JOB_ID_KEY);
  if (existingId) {
    try {
      await context.scheduler.cancelJob(existingId);
      console.log(
        `digest: cancelled old job ${existingId} (was cron="${current ?? '?'}")`,
      );
    } catch (e) {
      console.error(`digest: could not cancel old job ${existingId}: ${e}`);
    }
  }

  try {
    const jobId = await context.scheduler.runJob({
      name: DIGEST_JOB,
      cron: desired,
    });
    await context.redis.set(DIGEST_JOB_ID_KEY, jobId);
    await context.redis.set(DIGEST_CRON_KEY, desired);
    console.log(`digest: scheduled with cron "${desired}" (jobId=${jobId})`);
  } catch (e) {
    console.error(`digest: failed to schedule with cron "${desired}": ${e}`);
  }
}

async function ensureHeartbeatScheduled(context: Context): Promise<void> {
  const existingId = await context.redis.get(HEARTBEAT_JOB_ID_KEY);
  if (existingId) {
    console.log(`heartbeat: already scheduled (jobId=${existingId})`);
    return;
  }

  try {
    const jobId = await context.scheduler.runJob({
      name: HEARTBEAT_JOB,
      cron: HEARTBEAT_CRON,
    });
    await context.redis.set(HEARTBEAT_JOB_ID_KEY, jobId);
    console.log(
      `heartbeat: scheduled with cron "${HEARTBEAT_CRON}" (jobId=${jobId})`,
    );
  } catch (e) {
    console.error(`heartbeat: failed to schedule: ${e}`);
  }
}

// ---------------------------------------------------------------------------
// !define <term>
// ---------------------------------------------------------------------------
Devvit.addTrigger({
  event: 'CommentSubmit',
  onEvent: async (event, context) => {
    if (!event.comment) return;
    const body = event.comment.body;

    // Fast path: if neither `!define` nor `u/` appears, don't even bother
    // loading config. Saves a Redis hit on every comment in the subreddit.
    const bodyLower = body.toLowerCase();
    if (!bodyLower.includes(COMMAND.toLowerCase())) return;

    const config = await loadConfig(context);

    // Skip the bot's own comments (avoids any loop if the footer ever
    // contains the command prefix).
    const author = event.author?.name?.toLowerCase() ?? '';
    if (author && author === config.bot_username) {
      console.log(`define: ignoring own comment ${event.comment.id}`);
      return;
    }

    const parsed = parseCommand(body, config);
    if (!parsed) {
      console.log(
        `define: comment ${event.comment.id} contains "${COMMAND}" but no valid invocation (missing summon or prefix); skipping`,
      );
      return;
    }

    const { term, mode } = parsed;
    console.log(
      `define: mode=${mode} term="${term}" comment=${event.comment.id} author=${author || '?'}`,
    );

    const footer = '\n\n---\n' + config.reply.footer;
    const termLower = term.toLowerCase();

    // Blocklist check
    if (
      config.blocked_terms.length > 0 &&
      config.blocked_terms.some((b) => termLower === b || termLower.includes(b))
    ) {
      console.log(`define: "${term}" matched blocklist; rejecting`);
      await replyWith(
        context,
        event.comment.id,
        renderTemplate(config.reply.off_topic_message, { term }) + footer,
      );
      return;
    }

    let replyText: string;
    try {
      const summary = await lookupTerm(term);
      if (!summary) {
        console.log(`define: no Wikipedia article for "${term}"`);
        replyText =
          renderTemplate(config.reply.not_found_message, { term }) + footer;
      } else {
        const cats = await fetchCategories(summary.title);
        if (!isAllowedTopic(cats, config)) {
          const preview = cats.slice(0, 8).join(', ') + (cats.length > 8 ? ', ...' : '');
          console.log(
            `define: "${summary.title}" rejected as off-topic; categories=[${preview}]`,
          );
          replyText =
            renderTemplate(config.reply.off_topic_message, { term }) + footer;
        } else {
          console.log(
            `define: "${summary.title}" accepted (${cats.length} categories)`,
          );
          const extract = firstSentences(
            summary.extract,
            config.reply.summary_sentences,
          );
          replyText =
            `**${summary.title}**\n\n${extract}\n\n` +
            `[Read more](${summary.content_urls.desktop.page})` +
            footer;
        }
      }
    } catch (e) {
      console.error(`define: lookup failed for "${term}": ${e}`);
      replyText = config.reply.error_message + footer;
    }

    await replyWith(context, event.comment.id, replyText);
  },
});

async function replyWith(
  context: Context,
  commentId: string,
  text: string,
): Promise<void> {
  try {
    await context.reddit.submitComment({ id: commentId, text });
    console.log(`define: replied to ${commentId}`);
  } catch (e) {
    console.error(`define: could not submit reply to ${commentId}: ${e}`);
  }
}

// ---------------------------------------------------------------------------
// Weekly mod digest job
// ---------------------------------------------------------------------------
Devvit.addSchedulerJob({
  name: DIGEST_JOB,
  onRun: async (_, context) => {
    const config = await loadConfig(context);
    const subreddit = await context.reddit.getCurrentSubreddit();
    const subredditName = subreddit.name;
    const page = config.mod_digest.wiki_page;

    console.log(
      `digest: firing; reading wiki page "${page}" on r/${subredditName}`,
    );

    let content: string;
    try {
      const wiki = await context.reddit.getWikiPage(subredditName, page);
      content = wiki.content.trim();
    } catch (e) {
      console.error(`digest: could not read wiki page "${page}": ${e}`);
      return;
    }

    if (!content) {
      console.warn(
        `digest: wiki page "${page}" is empty — nothing to post this week`,
      );
      return;
    }
    if (content === BLANK_DIGEST) {
      console.warn(
        `digest: wiki page "${page}" still holds the blank placeholder "${BLANK_DIGEST}" — skipping`,
      );
      return;
    }

    let postId: string;
    try {
      const post = await context.reddit.submitPost({
        subredditName,
        title: config.mod_digest.post_title,
        text: content,
      });
      postId = post.id;
      console.log(
        `digest: submitted post ${postId} titled "${config.mod_digest.post_title}"`,
      );
    } catch (e) {
      console.error(`digest: failed to submit post: ${e}`);
      return;
    }

    try {
      await context.reddit.distinguish(postId, true);
      await context.reddit.sticky(postId, true);
      console.log(`digest: distinguished and stickied ${postId}`);
    } catch (e) {
      console.error(
        `digest: post ${postId} submitted but mod actions failed: ${e}`,
      );
    }

    try {
      await context.reddit.updateWikiPage({
        subredditName,
        page,
        content: BLANK_DIGEST,
        reason: 'bot: cleared after weekly digest post',
      });
      console.log(`digest: wiki page "${page}" reset for next week`);
    } catch (e) {
      console.error(`digest: could not reset wiki page: ${e}`);
    }
  },
});

// ---------------------------------------------------------------------------
// Heartbeat — re-read config and re-sync the digest schedule every 5 minutes,
// so config changes propagate even without subreddit activity.
// ---------------------------------------------------------------------------
Devvit.addSchedulerJob({
  name: HEARTBEAT_JOB,
  onRun: async (_, context) => {
    console.log('heartbeat: running config sync');
    try {
      const config = await loadConfig(context, { bypassCache: true });
      await ensureDigestScheduled(context, config);
    } catch (e) {
      console.error(`heartbeat: failed: ${e}`);
    }
  },
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
async function onInstallOrUpgrade(context: Context): Promise<void> {
  console.log('llmphysics-bot install/upgrade: scheduling jobs');
  // On upgrade, the old scheduler state may or may not survive. Clear
  // stored job IDs so ensureHeartbeatScheduled re-creates the heartbeat.
  try {
    await context.redis.del(HEARTBEAT_JOB_ID_KEY);
  } catch {
    /* non-fatal */
  }
  const config = await loadConfig(context, { bypassCache: true });
  await ensureDigestScheduled(context, config);
  await ensureHeartbeatScheduled(context);
}

Devvit.addTrigger({
  event: 'AppInstall',
  onEvent: async (_, context) => {
    await onInstallOrUpgrade(context);
  },
});

Devvit.addTrigger({
  event: 'AppUpgrade',
  onEvent: async (_, context) => {
    await onInstallOrUpgrade(context);
  },
});

export default Devvit;
