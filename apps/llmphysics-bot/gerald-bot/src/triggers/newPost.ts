import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { witness, pickOne } from '../persona/gerald';
import { logger } from '../lib/logger';

/**
 * "Filed." — Gerald witnesses the arrival of a working paper.
 *
 * Fires on PostSubmit when the post body matches paper-shape heuristics.
 * Heuristics only. No LLM. False positives are much worse than false negatives.
 */

const CFG = triggers.new_post;

export async function handleNewPost(context: TriggerContext, event: any): Promise<void> {
  if (!CFG.enabled) return;

  const post = event.post;
  if (!post) return;

  const body: string = (post.selftext || '').toString();
  const title: string = (post.title || '').toString();
  const combined = `${title}\n${body}`;

  if (combined.length < CFG.min_length_chars) return;

  const lower = combined.toLowerCase();
  let hits = 0;
  for (const markerPattern of CFG.paper_shape_markers) {
    try {
      if (new RegExp(markerPattern, 'i').test(lower)) hits++;
    } catch (e) {
      logger.error('newPost', `bad regex in triggers.new_post.paper_shape_markers: ${markerPattern}`, e);
    }
  }

  if (hits < CFG.required_marker_count) return;

  const word = pickOne(CFG.response_pool);
  if (!word) return;

  await witness(context, {
    postId: post.id,
    subreddit: event.subreddit?.name ?? 'unknown',
    word,
    triggerName: 'newPost',
  });
}
