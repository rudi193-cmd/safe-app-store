import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { speak, pickOne } from '../persona/hanz';
import { logger } from '../lib/logger';

/**
 * Fires on posts that look like a code question, debugging session, or
 * programming confession. Hanz has been here before. He shows up.
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
  for (const markerPattern of CFG.code_shape_markers) {
    try {
      if (new RegExp(markerPattern, 'i').test(lower)) hits++;
    } catch (e) {
      logger.error('newPost', `bad regex in triggers.new_post.code_shape_markers: ${markerPattern}`, e);
    }
  }

  if (hits < CFG.required_marker_count) return;

  const text = pickOne(CFG.response_pool);
  if (!text) return;

  await speak(context, {
    postId: post.id,
    subreddit: event.subreddit?.name ?? 'unknown',
    text,
    triggerName: 'newPost',
  });
}
