import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * The ΔΣ gaps catalog.
 *
 * Oakenscroll catalogs acknowledged unknowns. The target is 42.
 * He does not reduce the table. He only adds to it.
 *
 * Each entry: { description, submitter, timestamp }
 * Stored as a Redis list (most-recent-first). Counter tracked separately.
 */

const GAPS_KEY = 'oakenscroll:gaps';
const COUNTER_KEY = 'oakenscroll:delta_sigma';
const MAX_DISPLAY = 5;
const TARGET = 42;

export interface GapEntry {
  description: string;
  submitter: string;
  timestamp: number;
  [key: string]: string | number;
}

export async function addGap(
  context: TriggerContext,
  description: string,
  submitter: string,
): Promise<number> {
  const entry: GapEntry = { description, submitter, timestamp: Date.now() };
  await context.redis.zAdd(GAPS_KEY, { score: entry.timestamp, member: JSON.stringify(entry) });
  const count = await context.redis.incrBy(COUNTER_KEY, 1);
  logger.info('Gaps', `gap added by u/${submitter}. ΔΣ=${count}`);
  return count;
}

export async function getRecentGaps(
  context: TriggerContext,
  limit: number = MAX_DISPLAY,
): Promise<GapEntry[]> {
  try {
    const raw = await context.redis.zRange(GAPS_KEY, 0, limit - 1, { by: 'rank', reverse: true });
    return raw.map((r) => JSON.parse(r.member) as GapEntry);
  } catch (e) {
    logger.error('Gaps', 'zRange failed', e);
    return [];
  }
}

export async function getDeltaSigma(context: TriggerContext): Promise<number> {
  const raw = await context.redis.get(COUNTER_KEY);
  return raw ? parseInt(raw, 10) : 0;
}

export function formatDeltaSigma(count: number): string {
  if (count >= TARGET) return `ΔΣ=${count} — the table is full.`;
  const remaining = TARGET - count;
  return `ΔΣ=${count} / ${TARGET} — ${remaining} acknowledged unknowns remaining.`;
}
