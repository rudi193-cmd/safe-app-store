import type { TriggerContext } from '@devvit/public-api';
import { logger } from '../lib/logger';
import { getSpamStatus, isModerator } from '../lib/spamguard';
import { recordInteraction } from '../lib/flair';
import { addBug } from '../lib/bugs';
import { canAppear, recordAppearance } from '../lib/ratelimit';
import napkins from '../data/napkins.json';
import canon from '../data/canon.json';

/**
 * Summon handler. Hanz responds to explicit invocation.
 *
 * Commands (detected anywhere in comment body):
 *   !hanz              — Hanz witnesses and encourages
 *   !hanz bug <text>   — logs to the Known Bugs Registry
 *   !hanz spin         — Debug Roulette: a random koan from the napkin pile
 *
 * Spam guard: 5-min window, warn at 3, timeout at 4 (LLMPhysics pattern).
 * Summons bypass per-post cap but keep daily sub cap.
 */

const BOT_USERNAME = canon.account.username;

const SUMMON_RESPONSES = [
  'The candle is on. Bring the thing.',
  'I have been here. Copenhagen too.',
  'Witnessed. The corner is available.',
  "The code did not fail. The code found the edge. That's different.",
  "I've introduced this bug. It took a week. You're doing great.",
];

const SPAM_WARN_RESPONSE =
  'The corner keeps a log. Frequency noted. The candle is still on.';

const SPAM_BLOCK_RESPONSE =
  'The corner is currently closed. Bring the thing later. Not right now.';

type Command = 'bug' | 'spin' | 'bare';

function parseCommand(body: string): { command: Command; payload: string } | null {
  const lower = body.toLowerCase();

  if (!lower.includes('!hanz')) return null;

  // !hanz bug <payload>
  const bugMatch = body.match(/!hanz\s+bug\s+(.+)/i);
  if (bugMatch) {
    const payload = bugMatch[1].split(/[.?!\n]/)[0].trim().slice(0, 200);
    if (payload) return { command: 'bug', payload };
  }

  // !hanz spin
  if (/!hanz\s+spin\b/i.test(body)) {
    return { command: 'spin', payload: '' };
  }

  // bare !hanz
  return { command: 'bare', payload: '' };
}

function pickNapkin(): string {
  if (Math.random() < napkins.rare_phrase_chance && napkins.rare_phrases.length > 0) {
    return napkins.rare_phrases[Math.floor(Math.random() * napkins.rare_phrases.length)];
  }
  const words = napkins.words.filter((w: string) => !/TODO/i.test(w));
  if (words.length === 0) return '🕯️';
  return words[Math.floor(Math.random() * words.length)];
}

export async function handleSummon(context: TriggerContext, event: any): Promise<void> {
  const comment = event.comment;
  if (!comment) return;

  const author = event.author?.name;
  if (!author) return;

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

  if (!(await canAppear(context, subreddit))) {
    logger.info('Summon', `daily cap reached in r/${subreddit}`);
    return;
  }

  const prefix = spamStatus === 1 ? `${SPAM_WARN_RESPONSE} ` : '';
  let replyText: string;

  if (parsed.command === 'bug') {
    const entry = await addBug(context, parsed.payload, author);
    replyText = `${prefix}Bug #${entry.id} logged. Status: Open. The corner has it.`;
  } else if (parsed.command === 'spin') {
    const koan = pickNapkin();
    replyText = `${prefix}${koan}`;
  } else {
    replyText = prefix + SUMMON_RESPONSES[Math.floor(Math.random() * SUMMON_RESPONSES.length)];
  }

  try {
    await context.reddit.submitComment({ id: comment.id, text: replyText });
    await recordAppearance(context, subreddit);
    await recordInteraction(context, author, subreddit);
    logger.info('Summon', `replied to !hanz from u/${author}: "${replyText}"`);
  } catch (e) {
    logger.error('Summon', 'submitComment failed', e);
  }
}
