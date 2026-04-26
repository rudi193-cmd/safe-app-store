import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import napkins from '../data/napkins.json';
import { speak } from '../persona/hanz';
import { logger } from '../lib/logger';

/**
 * Scheduled candlelit appearance. Hanz has passed through and left something
 * on the table. No explanation. The candle is still on.
 */

const CFG = triggers.napkin_drop;

function pickNapkin(): string | null {
  if (Math.random() < napkins.rare_phrase_chance && napkins.rare_phrases.length > 0) {
    return napkins.rare_phrases[Math.floor(Math.random() * napkins.rare_phrases.length)];
  }

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
  const text = pickNapkin();
  if (!text) return;

  await speak(context, {
    postId: target.id,
    subreddit: subName,
    text,
    triggerName: 'napkinDrop',
  });
}
