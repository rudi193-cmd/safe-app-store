import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { witness, pickOne } from '../persona/gerald';
import { logger } from '../lib/logger';

/**
 * Polls recent hot posts on each heartbeat and witnesses those that have
 * crossed a score threshold since the last check. One witness per post,
 * ever — enforced by the per-post cap in persona/gerald.ts#witness.
 *
 * Devvit doesn't expose a score-change trigger, so this is a pull model
 * driven by the heartbeat scheduler job.
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

  const thresholds = [...CFG.thresholds].sort((a, b) => b - a); // descending

  for (const post of posts) {
    const score = post.score ?? 0;
    const crossed = thresholds.find((t) => score >= t);
    if (crossed === undefined) continue;

    const word = pickOne(CFG.response_pool);
    if (!word) continue;

    // witness() handles the "already witnessed this post" check, so looping
    // through hot posts every heartbeat is safe and idempotent.
    await witness(context, {
      postId: post.id,
      subreddit: subName,
      word,
      triggerName: `scoreMilestone:${crossed}`,
    });
  }
}
