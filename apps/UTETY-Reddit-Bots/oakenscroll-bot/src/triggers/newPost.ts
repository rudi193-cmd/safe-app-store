import type { TriggerContext } from '@devvit/public-api';
import triggers from '../data/triggers.json';
import { speak, pickOne } from '../persona/oakenscroll';
import { logger } from '../lib/logger';

/**
 * Oakenscroll observes posts in his domain: LLM physics, theoretical physics,
 * coordinate systems, consciousness, ontology. Drops a cryptic observation.
 *
 * One domain marker match is enough — his domain is broad and his appearances
 * are rate-limited. False negatives are fine; false positives are not.
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
  for (const markerPattern of CFG.domain_markers) {
    try {
      if (new RegExp(markerPattern, 'i').test(lower)) hits++;
    } catch (e) {
      logger.error('newPost', `bad regex in triggers.new_post.domain_markers: ${markerPattern}`, e);
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
