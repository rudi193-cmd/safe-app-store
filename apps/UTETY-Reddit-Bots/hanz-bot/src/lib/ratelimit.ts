import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * Per-subreddit daily appearance cap. Hanz is warm but not omnipresent.
 * Cap stored as a Redis counter keyed by UTC day, 48h TTL.
 */

const DEFAULT_DAILY_CAP = 5;

function dayKey(subreddit: string): string {
  const d = new Date();
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `hanz:ratelimit:${subreddit}:${y}-${m}-${day}`;
}

export async function canAppear(
  context: TriggerContext,
  subreddit: string,
  cap: number = DEFAULT_DAILY_CAP,
): Promise<boolean> {
  const key = dayKey(subreddit);
  const raw = await context.redis.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  return count < cap;
}

export async function recordAppearance(
  context: TriggerContext,
  subreddit: string,
): Promise<void> {
  const key = dayKey(subreddit);
  const count = await context.redis.incrBy(key, 1);
  if (count === 1) {
    await context.redis.expire(key, 60 * 60 * 48);
  }
  logger.info('Ratelimit', `appearance #${count} in r/${subreddit} today`);
}

export async function hasWitnessedPost(
  context: TriggerContext,
  postId: string,
): Promise<boolean> {
  const v = await context.redis.get(`hanz:witnessed:${postId}`);
  return !!v;
}

export async function markPostWitnessed(
  context: TriggerContext,
  postId: string,
): Promise<void> {
  await context.redis.set(`hanz:witnessed:${postId}`, '1', {
    expiration: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30),
  });
}
