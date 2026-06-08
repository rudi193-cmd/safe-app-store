import type { TriggerContext } from '@devvit/public-api';

/**
 * Per-author cooldown. A user who triggered a witnessing once cannot trigger
 * another of the same trigger-type for N hours. Prevents Gerald from dogpiling
 * a single poster.
 */

export async function isOnCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
): Promise<boolean> {
  const v = await context.redis.get(`gerald:cooldown:${triggerName}:${username}`);
  return !!v;
}

export async function setCooldown(
  context: TriggerContext,
  triggerName: string,
  username: string,
  hours: number,
): Promise<void> {
  await context.redis.set(
    `gerald:cooldown:${triggerName}:${username}`,
    '1',
    { expiration: new Date(Date.now() + hours * 60 * 60 * 1000) },
  );
}
