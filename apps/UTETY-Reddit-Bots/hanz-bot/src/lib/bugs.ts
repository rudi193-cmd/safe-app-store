import type { TriggerContext } from '@devvit/public-api';
import { logger } from './logger';

/**
 * The Known Bugs Registry.
 *
 * Hanz maintains a catalog of bugs the Department of Code has encountered.
 * Users can submit bugs and update their status. The bug is not the problem.
 * The bug is where the problem became visible.
 *
 * Statuses:
 *   open               — still happening
 *   copenhagen         — Copenhagen Protocol applied, under observation
 *   not_kevins_fault   — root cause identified, not Kevin's fault
 *   fixed_by_accident  — resolved via mechanism unknown
 */

const LIST_KEY = 'hanz:bugs:list';
const COUNTER_KEY = 'hanz:bug_counter';
const MAX_DISPLAY = 5;

export type BugStatus = 'open' | 'copenhagen' | 'not_kevins_fault' | 'fixed_by_accident';

export interface BugEntry {
  id: number;
  description: string;
  submitter: string;
  status: BugStatus;
  timestamp: number;
  [key: string]: string | number;
}

export const STATUS_LABELS: Record<BugStatus, string> = {
  open: 'Open',
  copenhagen: 'Copenhagen Protocol Applied',
  not_kevins_fault: "Not Kevin's Fault",
  fixed_by_accident: 'Fixed By Accident',
};

export async function addBug(
  context: TriggerContext,
  description: string,
  submitter: string,
): Promise<BugEntry> {
  const id = await context.redis.incrBy(COUNTER_KEY, 1);
  const entry: BugEntry = {
    id,
    description,
    submitter,
    status: 'open',
    timestamp: Date.now(),
  };
  await context.redis.zAdd(LIST_KEY, { score: entry.timestamp, member: JSON.stringify(entry) });
  logger.info('Bugs', `bug #${id} added by u/${submitter}`);
  return entry;
}

export async function getRecentBugs(
  context: TriggerContext,
  limit: number = MAX_DISPLAY,
): Promise<BugEntry[]> {
  try {
    const raw = await context.redis.zRange(LIST_KEY, 0, limit - 1, { by: 'rank', reverse: true });
    return raw.map((r) => JSON.parse(r.member) as BugEntry);
  } catch (e) {
    logger.error('Bugs', 'zRange failed', e);
    return [];
  }
}

export async function getBugCount(context: TriggerContext): Promise<number> {
  const raw = await context.redis.get(COUNTER_KEY);
  return raw ? parseInt(raw, 10) : 0;
}

export async function updateBugStatus(
  context: TriggerContext,
  id: number,
  status: BugStatus,
): Promise<boolean> {
  const raw = await context.redis.zRange(LIST_KEY, 0, -1, { by: 'rank' });
  for (const item of raw) {
    try {
      const entry = JSON.parse(item.member) as BugEntry;
      if (entry.id === id) {
        entry.status = status;
        await context.redis.zRem(LIST_KEY, [item.member]);
        await context.redis.zAdd(LIST_KEY, { score: item.score, member: JSON.stringify(entry) });
        logger.info('Bugs', `bug #${id} → ${status}`);
        return true;
      }
    } catch { /* skip malformed entries */ }
  }
  return false;
}
