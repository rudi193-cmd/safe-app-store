import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * Summon spam guard — lifted from LLMPhysics-bot pattern.
 *
 * Sliding 5-minute window per user. Moderators bypass entirely.
 *
 *   0  — proceed normally
 *   1  — warn (3rd call in window)
 *   2  — block (4th+ call, 30-min timeout set)
 */

const WINDOW_SECONDS = 300; // 5 minutes
const TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const WARN_AT = 3;
const BLOCK_AT = 4;

export type SpamStatus = 0 | 1 | 2;

export async function getSpamStatus(
  context: TriggerContext,
  username: string,
  isMod: boolean,
): Promise<SpamStatus> {
  if (isMod) return 0;

  const windowKey = `oakenscroll:spam:window:${username}`;
  const timeoutKey = `oakenscroll:spam:timeout:${username}`;

  const isTimedOut = await context.redis.get(timeoutKey);
  if (isTimedOut) {
    logger.info('SpamGuard', `u/${username} is timed out`);
    return 2;
  }

  const count = await context.redis.incrBy(windowKey, 1);
  if (count === 1) {
    await context.redis.expire(windowKey, WINDOW_SECONDS);
  }

  if (count >= BLOCK_AT) {
    await context.redis.set(timeoutKey, '1', {
      expiration: new Date(Date.now() + TIMEOUT_MS),
    });
    logger.info('SpamGuard', `u/${username} timed out (${count} calls in window)`);
    return 2;
  }

  if (count >= WARN_AT) {
    logger.info('SpamGuard', `u/${username} warned (${count} calls in window)`);
    return 1;
  }

  return 0;
}

export async function isModerator(context: TriggerContext, username: string): Promise<boolean> {
  try {
    const sub = await context.reddit.getCurrentSubreddit();
    const mods = await context.reddit.getModerators({ subredditName: sub.name }).all();
    return mods.some((m) => m.username.toLowerCase() === username.toLowerCase());
  } catch {
    return false;
  }
}
