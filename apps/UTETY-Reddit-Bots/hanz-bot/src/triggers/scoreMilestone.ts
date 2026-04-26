import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { speak, pickOne } from '../persona/hanz';
import { logger } from '../lib/logger';

/**
 * Polls recent hot posts on each heartbeat. When a post crosses a score
 * threshold, Hanz acknowledges it. Per-post cap makes this idempotent.
 */

const CFG = triggers.score_milestone;

export async function pollScoreMilestones(context: TriggerContext): Promise<void> {
  if (!CFG.enabled) return;

  let subName: string;
  try {
    const sub = await context.reddit.getCurrentSubreddit();
    subName = sub.name;
  } catch (e) {
    logger.error('scoreMilestone', 'getCurrentSubreddit failed', e);
    return;
  }

  let posts: any[];
  try {
    posts = await context.reddit.getHotPosts({ subredditName: subName, limit: 25 }).all();
  } catch (e) {
    logger.error('scoreMilestone', 'getHotPosts failed', e);
    return;
  }

  const thresholds = [...CFG.thresholds].sort((a, b) => b - a);

  for (const post of posts) {
    const score = post.score ?? 0;
    const crossed = thresholds.find((t) => score >= t);
    if (crossed === undefined) continue;

    const text = pickOne(CFG.response_pool);
    if (!text) continue;

    await speak(context, {
      postId: post.id,
      subreddit: subName,
      text,
      triggerName: `scoreMilestone:${crossed}`,
    });
  }
}
