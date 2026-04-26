import type { TriggerContext } from '@devvit/public-api';
import { logger } from '../lib/logger';
import { getSpamStatus, isModerator } from '../lib/spamguard';
import { recordInteraction } from '../lib/flair';
import { addGap, getDeltaSigma, formatDeltaSigma } from '../lib/gaps';
import { canAppear, recordAppearance } from '../lib/ratelimit';
import canon from '../data/canon.json';

/**
 * Summon handler. Oakenscroll responds to explicit invocation.
 *
 * Commands (detected anywhere in comment body):
 *   !oak              — Oakenscroll observes and reframes
 *   !oak gap <text>   — files an acknowledged unknown to the ΔΣ catalog
 *   !oak frame        — Oakenscroll assesses the reference frame of the post
 *
 * Spam guard: 5-min window, warn at 3, timeout at 4 (LLMPhysics pattern).
 * Summons bypass per-post cap (user asked explicitly) but keep daily sub cap.
 */

const BOT_USERNAME = canon.account.username;

// Responses stay in voice. Never direct help. Always a reframing.
const SUMMON_RESPONSES = [
  'The observatory is unlocked. Knock twice.',
  'Witnessed. The frame is noted.',
  'You have named a coordinate. The system that contains it is not specified.',
  'The question is in the gap. The gap is load-bearing.',
  'Filed under: things that require a reference frame before they can be true.',
];

const FRAME_RESPONSES = [
  'The frame you are standing in does not contain the frame you are looking for.',
  'You have the coordinates. You are missing the coordinate system.',
  'This claim requires a frame. The frame has not been provided. The observatory has filed this.',
  'Two observers. One system. The result depends on which one you are.',
];

const SPAM_WARN_RESPONSE =
  'The observatory logs every approach. The frequency is noted.';

const SPAM_BLOCK_RESPONSE =
  'The observatory is currently closed. Knock twice. Not four times.';

type Command = 'gap' | 'frame' | 'bare';

function parseCommand(body: string): { command: Command; payload: string } | null {
  const lower = body.toLowerCase();

  // Must contain !oak
  if (!lower.includes('!oak')) return null;

  // !oak gap <payload>
  const gapMatch = body.match(/!oak\s+gap\s+(.+)/i);
  if (gapMatch) {
    const payload = gapMatch[1].split(/[.?!\n]/)[0].trim().slice(0, 200);
    if (payload) return { command: 'gap', payload };
  }

  // !oak frame
  if (/!oak\s+frame\b/i.test(body)) {
    return { command: 'frame', payload: '' };
  }

  // bare !oak
  return { command: 'bare', payload: '' };
}

export async function handleSummon(context: TriggerContext, event: any): Promise<void> {
  const comment = event.comment;
  if (!comment) return;

  const author = event.author?.name;
  if (!author) return;

  // Never respond to self
  if (author.toLowerCase() === BOT_USERNAME.toLowerCase()) return;

  const body: string = comment.body || '';
  const parsed = parseCommand(body);
  if (!parsed) return;

  const postId: string = comment.postId ?? comment.linkId ?? '';
  const subreddit: string = event.subreddit?.name ?? '';

  if (!postId || !subreddit) {
    logger.error('Summon', 'missing postId or subreddit');
    return;
  }

  const mod = await isModerator(context, author);
  const spamStatus = await getSpamStatus(context, author, mod);

  if (spamStatus === 2) {
    try {
      await context.reddit.submitComment({ id: comment.id, text: SPAM_BLOCK_RESPONSE });
    } catch (e) {
      logger.error('Summon', 'spam block reply failed', e);
    }
    return;
  }

  // Daily sub cap still applies
  if (!(await canAppear(context, subreddit))) {
    logger.info('Summon', `daily cap reached in r/${subreddit}`);
    return;
  }

  const prefix = spamStatus === 1 ? `${SPAM_WARN_RESPONSE} ` : '';
  let replyText: string;

  if (parsed.command === 'gap') {
    const count = await addGap(context, parsed.payload, author);
    replyText = `${prefix}Acknowledged. ${formatDeltaSigma(count)}`;
  } else if (parsed.command === 'frame') {
    replyText = prefix + FRAME_RESPONSES[Math.floor(Math.random() * FRAME_RESPONSES.length)];
  } else {
    replyText = prefix + SUMMON_RESPONSES[Math.floor(Math.random() * SUMMON_RESPONSES.length)];
  }

  try {
    await context.reddit.submitComment({ id: comment.id, text: replyText });
    await recordAppearance(context, subreddit);
    await recordInteraction(context, author, subreddit);
    logger.info('Summon', `replied to !oak from u/${author}: "${replyText}"`);
  } catch (e) {
    logger.error('Summon', 'submitComment failed', e);
  }
}
