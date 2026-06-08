import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { speak, pickOne } from '../persona/hanz';
import { isOnCooldown, setCooldown } from '../lib/cooldown';
import { logger } from '../lib/logger';

/**
 * The stuck-ness detector. Hanz's unique trigger.
 *
 * newPost detects the technical shape of a debugging post. debuggingWitness
 * detects the emotional texture: the person has been stuck for a while, is
 * frustrated, and is running out of ideas. That's when Hanz shows up with
 * the candle.
 *
 * Strict by design. The warmth only works if it's rare and felt.
 */

const CFG = triggers.debugging_witness;

function countMatches(text: string, patterns: string[]): number {
  let n = 0;
  for (const pat of patterns) {
    try {
      const re = new RegExp(pat, 'gi');
      const matches = text.match(re);
      if (matches) n += matches.length;
    } catch (e) {
      logger.error('debuggingWitness', `bad regex: ${pat}`, e);
    }
  }
  return n;
}

export async function handleDebuggingWitness(context: TriggerContext, event: any): Promise<void> {
  if (!CFG.enabled) return;

  const post = event.post;
  if (!post) return;

  const author = event.author?.name;
  if (!author) return;

  const body: string = (post.selftext || '').toString();
  const title: string = (post.title || '').toString();
  const combined = `${title}\n${body}`;

  if (combined.length < CFG.min_length_chars) return;

  const stuck = countMatches(combined, CFG.stuck_markers);
  if (stuck < CFG.required_stuck_count) return;

  // per-author cooldown — Hanz shows up once, not every time they post
  if (await isOnCooldown(context, 'debuggingWitness', author)) {
    logger.info('debuggingWitness', `cooldown active for u/${author}`);
    return;
  }

  const text = pickOne(CFG.response_pool);
  if (!text) return;

  const spoke = await speak(context, {
    postId: post.id,
    subreddit: event.subreddit?.name ?? 'unknown',
    text,
    triggerName: 'debuggingWitness',
  });

  if (spoke) {
    await setCooldown(context, 'debuggingWitness', author, CFG.author_cooldown_hours);
  }
}
