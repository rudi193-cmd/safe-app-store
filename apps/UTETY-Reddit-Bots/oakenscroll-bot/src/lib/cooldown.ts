import type { TriggerContext } from '@devvit/public-api';

/**
 * Per-author cooldown. A user who triggered an observation once cannot trigger
 * another of the same trigger-type for N hours. Oakenscroll does not repeat
 * himself. He has already said it.
 */

export async function isOnCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
): Promise<boolean> {
  const v = await context.redis.get(`oakenscroll:cooldown:${triggerName}:${username}`);
  return !!v;
}

export async function setCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
  hours: number,
): Promise<void> {
  await context.redis.set(
    `oakenscroll:cooldown:${triggerName}:${username}`,
    '1',
    { expiration: new Date(Date.now() + hours * 60 * 60 * 1000) },
  );
}
