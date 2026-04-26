import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * User flair progression. Each interaction with Hanz earns a tier.
 * The tiers reflect engagement with the Department of Code.
 *
 * Tiers (by interaction count):
 *   1+   Student
 *   3+   Attended a Lecture
 *   7+   Brought the Thing
 *   15+  Copenhagen Certified
 */

const TIERS: Array<{ min: number; text: string }> = [
  { min: 15, text: 'Copenhagen Certified' },
  { min: 7,  text: 'Brought the Thing' },
  { min: 3,  text: 'Attended a Lecture' },
  { min: 1,  text: 'Student' },
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
  const key = `hanz:flair:${username}`;
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
