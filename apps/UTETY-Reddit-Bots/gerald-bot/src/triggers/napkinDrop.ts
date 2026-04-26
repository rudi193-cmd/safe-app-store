import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import napkins from '../data/napkins.json';
import { witness } from '../persona/gerald';
import { logger } from '../lib/logger';

/**
 * Scheduled napkin drops. Gerald appears on a recent post with a single
 * napkin word — no context, no trigger, no reason. Ported from the daughters'
 * "napkin letters that made no sense appear in document" idea.
 *
 * Scheduled via cron (see triggers.napkin_drop.cron). Each scheduled run only
 * drops with `chance_per_run` probability, so even the schedule is uncertain.
 *
 * The rare_emojis Easter egg (△, etc.) is the Bill Cipher pyramid port.
 */

const CFG = triggers.napkin_drop;

function pickNapkin(): string | null {
  if (Math.random() < napkins.rare_emoji_chance && napkins.rare_emojis.length > 0) {
    return napkins.rare_emojis[Math.floor(Math.random() * napkins.rare_emojis.length)];
  }

  // Weighted 1:1 between word and common-emoji pools by default.
  const useEmoji = Math.random() < 0.5 && napkins.emojis_common.length > 0;
  if (useEmoji) {
    return napkins.emojis_common[Math.floor(Math.random() * napkins.emojis_common.length)];
  }

  const words = napkins.words.filter((w: string) => !/TODO/i.test(w));
  if (words.length === 0) {
    logger.info('napkinDrop', 'no non-stub words in napkins.json — staying silent');
    return null;
  }
  return words[Math.floor(Math.random() * words.length)];
}

export async function runNapkinDrop(context: TriggerContext): Promise<void> {
  if (!CFG.enabled) return;
  if (Math.random() > CFG.chance_per_run) {
    logger.info('napkinDrop', 'chance_per_run rolled low; no drop this run');
    return;
  }

  let subName: string;
  try {
    const sub = await context.reddit.getCurrentSubreddit();
    subName = sub.name;
  } catch (e) {
    logger.error('napkinDrop', 'getCurrentSubreddit failed', e);
    return;
  }

  let posts: any[];
  try {
    posts = await context.reddit.getNewPosts({ subredditName: subName, limit: 10 }).all();
  } catch (e) {
    logger.error('napkinDrop', 'getNewPosts failed', e);
    return;
  }

  const windowMs = CFG.target_window_hours * 60 * 60 * 1000;
  const now = Date.now();
  const eligible = posts.filter((p) => {
    const created = (p.createdAt?.getTime?.() ?? 0);
    return created > 0 && now - created < windowMs;
  });

  if (eligible.length === 0) {
    logger.info('napkinDrop', 'no eligible recent posts');
    return;
  }

  const target = eligible[Math.floor(Math.random() * eligible.length)];
  const word = pickNapkin();
  if (!word) return;

  await witness(context, {
    postId: target.id,
    subreddit: subName,
    word,
    triggerName: 'napkinDrop',
  });
}
