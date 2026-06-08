import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { speak, pickOne } from '../persona/oakenscroll';
import { isOnCooldown, setCooldown } from '../lib/cooldown';
import { logger } from '../lib/logger';

/**
 * The reference frame detector. Oakenscroll's counterpart to Gerald's zero-gaps.
 *
 * Gerald detects posts whose asserter has been removed (first-person claims with
 * zero epistemic hedging). Oakenscroll detects a different failure: posts that
 * make strong claims without acknowledging the reference frame the claim is made
 * from. A claim can be confident AND epistemically honest — what Oakenscroll
 * flags is the assumption that no frame is needed.
 *
 * Strict by design. False positives destroy the character.
 */

const CFG = triggers.ref_frame;

function countMatches(text: string, patterns: string[]): number {
  let n = 0;
  for (const pat of patterns) {
    try {
      const re = new RegExp(pat, 'gi');
      const matches = text.match(re);
      if (matches) n += matches.length;
    } catch (e) {
      logger.error('refFrame', `bad regex: ${pat}`, e);
    }
  }
  return n;
}

export async function handleRefFrame(context: TriggerContext, event: any): Promise<void> {
  if (!CFG.enabled) return;

  const post = event.post;
  if (!post) return;

  const author = event.author?.name;
  if (!author) return;

  const body: string = (post.selftext || '').toString();
  const title: string = (post.title || '').toString();
  const combined = `${title}\n${body}`;

  if (combined.length < CFG.min_length_chars) return;

  const claims = countMatches(combined, CFG.claim_markers);
  const frames = countMatches(combined, CFG.frame_markers);

  if (claims < CFG.min_claim_hits) return;
  if (frames > CFG.max_frame_hits) return;

  // per-author cooldown so Oakenscroll doesn't follow a single poster around
  if (await isOnCooldown(context, 'refFrame', author)) {
    logger.info('refFrame', `cooldown active for u/${author}`);
    return;
  }

  const text = pickOne(CFG.response_pool);
  if (!text) return;

  const spoke = await speak(context, {
    postId: post.id,
    subreddit: event.subreddit?.name ?? 'unknown',
    text,
    triggerName: 'refFrame',
  });

  if (spoke) {
    await setCooldown(context, 'refFrame', author, CFG.author_cooldown_hours);
  }
}
