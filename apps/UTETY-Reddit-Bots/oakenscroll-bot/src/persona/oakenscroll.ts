import type { TriggerContext } from '@devvit/public-api';
import { logger } from '../lib/logger';
import canon from '../data/canon.json';
import { canAppear, recordAppearance, hasWitnessedPost, markPostWitnessed } from '../lib/ratelimit';

/**
 * Oakenscroll's persona module. Character constraints from canon.json become
 * executable rules here. Re-read the canon before relaxing anything.
 *
 *   - can_speak: true              -> multi-word responses allowed, max 280 chars
 *   - register: academic-formal    -> cryptic, aphoristic, never direct help
 *   - never_follows_up: true       -> one observation per post, ever
 *   - never_responds_to_replies    -> if parent comment is Oakenscroll, stay silent
 *   - always_reframes: true        -> the observation is a reframing, not an answer
 */

const BOT_USERNAME = canon.account.username;

/**
 * Output sanitizer. Every outbound string MUST pass this. If sanitize returns
 * null, Oakenscroll says nothing.
 *
 * Rules:
 *   - trimmed length > 0 and <= 280 chars
 *   - no URLs
 *   - no @mentions
 *   - no hashtags
 *   - no newlines (single-line observations only)
 *   - must contain at least one letter or digit (no pure punctuation drops)
 */
export function sanitize(raw: string): string | null {
  if (!raw) return null;
  const t = raw.trim();
  if (!t) return null;
  if (t.length > 280) return null;
  if (/[\n\r]/.test(t)) return null;
  if (/^https?:\/\//i.test(t)) return null;
  if (/@\w/.test(t)) return null;
  if (/#\w/.test(t)) return null;
  if (!/[\p{L}\p{N}]/u.test(t)) return null;
  return t;
}

/**
 * Pick a random element from a non-empty array. Returns null for empty.
 */
export function pickOne<T>(pool: T[]): T | null {
  if (!pool || pool.length === 0) return null;
  return pool[Math.floor(Math.random() * pool.length)];
}

/**
 * Speak wrapper. Every trigger funnels output through this — applies the
 * sanitizer, per-post cap, per-subreddit daily cap, then posts the comment.
 * Returns true if Oakenscroll actually spoke.
 */
export async function speak(
  context: TriggerContext,
  opts: {
    commentId?: string;
    postId: string;
    subreddit: string;
    parentAuthor?: string;
    text: string;
    triggerName: string;
  },
): Promise<boolean> {
  // never_responds_to_replies: if we're replying to Oakenscroll, stay silent.
  if (opts.parentAuthor && opts.parentAuthor === BOT_USERNAME) {
    logger.info('Oakenscroll', `skip: would reply to self in ${opts.postId}`);
    return false;
  }

  // canon-level enforcement: only speak if the account is configured
  if (BOT_USERNAME.startsWith('TODO_REPLACE')) {
    logger.error('Oakenscroll', 'skip: BOT_USERNAME not configured in canon.json');
    return false;
  }

  // per-post cap
  if (await hasWitnessedPost(context, opts.postId)) {
    logger.info('Oakenscroll', `skip: already spoke on ${opts.postId}`);
    return false;
  }

  // per-sub daily cap
  if (!(await canAppear(context, opts.subreddit))) {
    logger.info('Oakenscroll', `skip: daily cap reached in r/${opts.subreddit}`);
    return false;
  }

  const output = sanitize(opts.text);
  if (!output) {
    logger.error('Oakenscroll', `sanitize rejected "${opts.text}" from ${opts.triggerName}`);
    return false;
  }

  try {
    await context.reddit.submitComment({
      id: opts.commentId ?? opts.postId,
      text: output,
    });
    await markPostWitnessed(context, opts.postId);
    await recordAppearance(context, opts.subreddit);
    logger.info('Oakenscroll', `spoke: "${output}" on ${opts.postId} via ${opts.triggerName}`);
    return true;
  } catch (e) {
    logger.error('Oakenscroll', 'submitComment failed', e);
    return false;
  }
}
