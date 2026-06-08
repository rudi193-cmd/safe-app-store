import type { TriggerContext } from '@devvit/public-api';
import { logger } from '../lib/logger';
import canon from '../data/canon.json';
import { canAppear, recordAppearance, hasWitnessedPost, markPostWitnessed } from '../lib/ratelimit';

/**
 * Hanz's persona module. Character constraints from canon.json become
 * executable rules here. Re-read the canon before relaxing anything.
 *
 *   - can_speak: true                -> multi-word responses, max 280 chars
 *   - register: chaotic-competent    -> warm, self-deprecating, accidentally wise
 *   - never_condescends: true        -> the bug is a colleague, not a failure
 *   - never_follows_up: true         -> one observation per post, ever
 *   - never_responds_to_replies      -> if parent comment is Hanz, stay silent
 */

const BOT_USERNAME = canon.account.username;

/**
 * Output sanitizer. Every outbound string MUST pass this.
 *
 * Rules:
 *   - trimmed length > 0 and <= 280 chars
 *   - no URLs
 *   - no @mentions
 *   - no hashtags
 *   - no newlines
 *   - must contain at least one letter or digit
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
 * Speak wrapper. Every trigger funnels output through this — sanitizer,
 * per-post cap, per-subreddit daily cap, then posts the comment.
 * Returns true if Hanz actually spoke.
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
  // never_responds_to_replies: if we're replying to Hanz, stay silent.
  if (opts.parentAuthor && opts.parentAuthor === BOT_USERNAME) {
    logger.info('Hanz', `skip: would reply to self in ${opts.postId}`);
    return false;
  }

  // per-post cap
  if (await hasWitnessedPost(context, opts.postId)) {
    logger.info('Hanz', `skip: already spoke on ${opts.postId}`);
    return false;
  }

  // per-sub daily cap
  if (!(await canAppear(context, opts.subreddit))) {
    logger.info('Hanz', `skip: daily cap reached in r/${opts.subreddit}`);
    return false;
  }

  const output = sanitize(opts.text);
  if (!output) {
    logger.error('Hanz', `sanitize rejected "${opts.text}" from ${opts.triggerName}`);
    return false;
  }

  try {
    await context.reddit.submitComment({
      id: opts.commentId ?? opts.postId,
      text: output,
    });
    await markPostWitnessed(context, opts.postId);
    await recordAppearance(context, opts.subreddit);
    logger.info('Hanz', `spoke: "${output}" on ${opts.postId} via ${opts.triggerName}`);
    return true;
  } catch (e) {
    logger.error('Hanz', 'submitComment failed', e);
    return false;
  }
}
