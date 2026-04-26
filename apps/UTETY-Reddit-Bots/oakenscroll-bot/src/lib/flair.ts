import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * User flair progression. Each interaction with Oakenscroll earns a tier.
 * The tiers are observational ranks — not gamified, just cataloged.
 *
 * Tiers (by interaction count):
 *   1+   Observer
 *   3+   Documented Observer
 *   7+   Frame-Aware
 *   15+  Adjacent to the Point
 */

const TIERS: Array<{ min: number; text: string }> = [
  { min: 15, text: 'Adjacent to the Point' },
  { min: 7,  text: 'Frame-Aware' },
  { min: 3,  text: 'Documented Observer' },
  { min: 1,  text: 'Observer' },
];

function tierFor(count: number): string | null {
  for (const tier of TIERS) {
    if (count >= tier.min) return tier.text;
  }
  return null;
}

export async function recordInteraction(
  context: TriggerContext,
  username: string,
  subredditName: string,
): Promise<void> {
  const key = `oakenscroll:flair:${username}`;
  const count = await context.redis.incrBy(key, 1);
  if (count === 1) {
    await context.redis.expire(key, 60 * 60 * 24 * 365); // 1 year
  }

  const flairText = tierFor(count);
  if (!flairText) return;

  try {
    await context.reddit.setUserFlair({
      subredditName,
      username,
      text: flairText,
    });
    logger.info('Flair', `u/${username} → "${flairText}" (${count} interactions)`);
  } catch (e) {
    logger.error('Flair', `setUserFlair failed for u/${username}`, e);
  }
}
