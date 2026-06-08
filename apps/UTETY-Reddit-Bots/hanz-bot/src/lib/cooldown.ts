import type { TriggerContext } from '@devvit/public-api';

/**
 * Per-author cooldown. Hanz doesn't pile on a single person. He shows up once,
 * says the thing, and lets the person work.
 */

export async function isOnCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
): Promise<boolean> {
  const v = await context.redis.get(`hanz:cooldown:${triggerName}:${username}`);
  return !!v;
}

export async function setCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
  hours: number,
): Promise<void> {
  await context.redis.set(
    `hanz:cooldown:${triggerName}:${username}`,
    '1',
    { expiration: new Date(Date.now() + hours * 60 * 60 * 1000) },
  );
}
