import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { witness, pickOne } from '../persona/gerald';
import { isOnCooldown, setCooldown } from '../lib/cooldown';
import { logger } from '../lib/logger';

/**
 * The letter-i theft, ported.
 *
 * The original daughters' idea was Gerald deleting every 'i' from a document —
 * removing the asserter from first-person singular claims. Reddit won't let a
 * bot edit posts, so the spirit survives as a DETECTOR: a post that makes
 * strong claims with zero epistemic hedging IS a document whose asserter has
 * effectively been removed. Gerald drops a 🍗 on it.
 *
 * Strict by design. False positives destroy the character.
 */

const CFG = triggers.zero_gaps;

function countMatches(text: string, patterns: string[]): number {
  let n = 0;
  for (const pat of patterns) {
    try {
      const re = new RegExp(pat, 'gi');
      const matches = text.match(re);
      if (matches) n += matches.length;
    } catch (e) {
      logger.error('zeroGaps', `bad regex: ${pat}`, e);
    }
  }
  return n;
}

export async function handleZeroGaps(context: TriggerContext, event: any): Promise<void> {
  if (!CFG.enabled) return;

  const post = event.post;
  if (!post) return;

  const author = event.author?.name;
  if (!author) return;

  const body: string = (post.selftext || '').toString();
  const title: string = (post.title || '').toString();
  const combined = `${title}\n${body}`;

  if (combined.length < CFG.min_length_chars) return;

  const confidence = countMatches(combined, CFG.confidence_markers);
  const gaps = countMatches(combined, CFG.gap_markers);

  if (confidence < CFG.min_confidence_hits) return;
  if (gaps > CFG.max_gap_hits) return;

  // per-author cooldown so Gerald doesn't dogpile a single user
  if (await isOnCooldown(context, 'zeroGaps', author)) {
    logger.info('zeroGaps', `cooldown active for u/${author}`);
    return;
  }

  const word = pickOne(CFG.response_pool);
  if (!word) return;

  const spoke = await witness(context, {
    postId: post.id,
    subreddit: event.subreddit?.name ?? 'unknown',
    word,
    triggerName: 'zeroGaps',
  });

  if (spoke) {
    await setCooldown(context, 'zeroGaps', author, CFG.author_cooldown_hours);
  }
}
