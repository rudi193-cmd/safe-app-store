import type { TriggerContext } from '@devvit/public-api';
import { logger } from '../lib/logger';
import canon from '../data/canon.json';
import { canAppear, recordAppearance, hasWitnessedPost, markPostWitnessed } from '../lib/ratelimit';

/**
 * Gerald's persona module. This file is where the character constraints from
 * canon.json become executable rules. If you are tempted to relax any of these
 * rules, stop and re-read the canon first.
 *
 *   - can_speak: false              -> output must be <= 1 token
 *   - never_explains: true          -> no footers, no disclosures, no "I'm a bot"
 *   - never_responds_to_replies:    -> if the parent comment is Gerald, drop it
 *   - timing_is_always_perfect:     -> scarcity enforced via ratelimit.ts
 */

const BOT_USERNAME = 'Spiritual-Sam-9582';

/**
 * Output sanitizer. Every outbound string MUST pass this. If sanitize returns
 * null, Gerald says nothing.
 *
 * Rules:
 *   - trimmed length > 0
 *   - no newlines
 *   - single token: either one word (optionally with a single trailing period)
 *     or a single emoji / single-character glyph.
 *   - nothing that looks like a URL, a sentence, a hashtag, or a mention.
 */
export function sanitize(raw: string): string | null {
  if (!raw) return null;
  const t = raw.trim();
  if (!t) return null;
  if (/\s/.test(t)) return null;                     // no whitespace -> no multi-word
  if (t.length > 24) return null;                    // pragmatic hard cap
  if (/[\n\r]/.test(t)) return null;
  if (/^https?:\/\//i.test(t)) return null;
  if (/^[#@]/.test(t)) return null;
  // Allow one trailing period on a word-token (e.g. "Filed.", "Witnessed.")
  // Allow a bare emoji / single glyph.
  const wordTok = /^[\p{L}\p{N}]+\.?$/u;
  const glyphTok = /^\p{Extended_Pictographic}$|^[\u25B3\u25BD\u25C7\u25A1\u2605\u2606]$/u;
  if (!wordTok.test(t) && !glyphTok.test(t)) return null;
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
 * Witness wrapper. Every trigger funnels its output through this — it applies
 * the sanitizer, the per-post cap, and the per-subreddit daily cap, and writes
 * the comment. Returns true if Gerald actually spoke (witnessed).
 */
export async function witness(
  context: TriggerContext,
  opts: {
    commentId?: string;
    postId: string;
    subreddit: string;
    parentAuthor?: string;
    word: string;
    triggerName: string;
  },
): Promise<boolean> {
  // never_responds_to_replies: if the thing we're about to reply to was authored
  // by Gerald, stay silent.
  if (opts.parentAuthor && opts.parentAuthor === BOT_USERNAME) {
    logger.info('Gerald', `skip: would reply to self in ${opts.postId}`);
    return false;
  }

  // canon-level enforcement
  if (!canon.properties.can_witness_threshold_crossings) {
    logger.info('Gerald', 'skip: witnessing disabled in canon');
    return false;
  }

  // per-post cap
  if (await hasWitnessedPost(context, opts.postId)) {
    logger.info('Gerald', `skip: already witnessed ${opts.postId}`);
    return false;
  }

  // per-sub daily cap
  if (!(await canAppear(context, opts.subreddit))) {
    logger.info('Gerald', `skip: daily cap reached in r/${opts.subreddit}`);
    return false;
  }

  const text = sanitize(opts.word);
  if (!text) {
    logger.error('Gerald', `sanitize rejected "${opts.word}" from ${opts.triggerName}`);
    return false;
  }

  try {
    await context.reddit.submitComment({
      id: opts.commentId ?? opts.postId,
      text,
    });
    await markPostWitnessed(context, opts.postId);
    await recordAppearance(context, opts.subreddit);
    logger.info('Gerald', `witnessed: "${text}" on ${opts.postId} via ${opts.triggerName}`);
    return true;
  } catch (e) {
    logger.error('Gerald', 'submitComment failed', e);
    return false;
  }
}
