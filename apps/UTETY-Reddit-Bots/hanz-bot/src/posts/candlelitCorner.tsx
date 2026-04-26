/** @jsx Devvit.createElement */
/** @jsxFrag Devvit.Fragment */

import { Devvit, useState, useAsync, useForm } from '@devvit/public-api';
import type { TriggerContext } from '@devvit/public-api';
import { addBug, getBugCount, getRecentBugs, updateBugStatus, STATUS_LABELS, type BugStatus } from '../lib/bugs';
import { recordInteraction } from '../lib/flair';
import napkins from '../data/napkins.json';
import { logger } from '../lib/logger';

/**
 * The Candlelit Corner — Hanz's interactive custom post type.
 *
 * Users can leave broken things on the table and track their status.
 * Debug Roulette gives a random koan from the napkin pile.
 * The candle is on. Bring your broken code and yourself.
 *
 * Rendered as a Devvit Blocks custom post. Posted weekly on Sunday evening.
 */

export const POST_TYPE_NAME = 'Candlelit Corner';

function pickNapkin(): string {
  if (Math.random() < napkins.rare_phrase_chance && napkins.rare_phrases.length > 0) {
    return napkins.rare_phrases[Math.floor(Math.random() * napkins.rare_phrases.length)];
  }
  const words = napkins.words.filter((w: string) => !/TODO/i.test(w));
  if (words.length === 0) return '🕯️';
  return words[Math.floor(Math.random() * words.length)];
}

export function registerCandlelitCorner(): void {
  Devvit.addCustomPostType({
    name: POST_TYPE_NAME,
    description: "The corner is lit. Bring your broken code and yourself.",
    height: 'tall',
    render: (context) => {
      const [rouletteResult, setRouletteResult] = useState<string | null>(null);
      const [refreshKey, setRefreshKey] = useState(0);

      const { data: bugData } = useAsync(
        async () => {
          const count = await getBugCount(context);
          const bugs = await getRecentBugs(context, 5);
          return { count, bugs };
        },
        { depends: refreshKey },
      );

      const submitForm = useForm(
        {
          title: 'Leave Something on the Table',
          description: 'Bring the broken thing. Hanz will witness it.',
          fields: [
            {
              type: 'string',
              name: 'bug',
              label: 'What is broken?',
              helpText: 'Describe the bug, error, or stuck-ness. One thing at a time.',
              required: true,
            },
          ],
        },
        async (values) => {
          const description = values.bug as string;
          const username = (await context.reddit.getCurrentUser())?.username ?? 'unknown';
          const subreddit = (await context.reddit.getCurrentSubreddit()).name;

          const entry = await addBug(context, description, username);
          await recordInteraction(context, username, subreddit);
          context.ui.showToast({ text: `Bug #${entry.id} logged. The corner has it.` });
          setRefreshKey((k: number) => k + 1);
        },
      );

      const updateForm = useForm(
        {
          title: 'Update Bug Status',
          description: 'How is the bug doing?',
          fields: [
            {
              type: 'number',
              name: 'id',
              label: 'Bug #',
              required: true,
            },
            {
              type: 'select',
              name: 'status',
              label: 'New status',
              options: [
                { label: 'Open', value: 'open' },
                { label: 'Copenhagen Protocol Applied', value: 'copenhagen' },
                { label: "Not Kevin's Fault", value: 'not_kevins_fault' },
                { label: 'Fixed By Accident', value: 'fixed_by_accident' },
              ],
              required: true,
            },
          ],
        },
        async (values) => {
          const id = values.id as number;
          const status = (values.status as string[])[0] as BugStatus;
          const updated = await updateBugStatus(context, id, status);
          if (updated) {
            context.ui.showToast({ text: `Bug #${id} → ${STATUS_LABELS[status]}` });
            setRefreshKey((k: number) => k + 1);
          } else {
            context.ui.showToast({ text: `Bug #${id} not found.` });
          }
        },
      );

      const count = bugData?.count ?? 0;
      const bugs = bugData?.bugs ?? [];

      return (
        <vstack height="100%" width="100%" padding="medium" gap="medium" backgroundColor="#1a1209">
          {/* Header */}
          <vstack gap="small">
            <hstack gap="small" alignment="start middle">
              <text size="xlarge" weight="bold" color="white">THE CANDLELIT CORNER</text>
              <text size="xlarge">🕯️</text>
            </hstack>
            <text size="small" color="#a07850">Department of Code, UTETY</text>
            <text size="small" color="#c9b37a">
              {count === 0
                ? 'Nothing on the table yet.'
                : `${count} thing${count === 1 ? '' : 's'} on the table.`}
            </text>
          </vstack>

          {/* Divider */}
          <hstack width="100%" height="1px" backgroundColor="#3d2e1a" />

          {/* Known bugs */}
          <vstack gap="small" grow>
            <text size="medium" weight="bold" color="#e8c97a">Known Bugs</text>
            {bugs.length === 0 ? (
              <text size="small" color="#a07850">
                The table is clear. Bring something.
              </text>
            ) : (
              bugs.map((bug, i) => (
                <hstack key={String(i)} gap="small" alignment="start top">
                  <text size="small" color="#c9b37a">#{bug.id}</text>
                  <vstack grow>
                    <text size="small" color="#e8c97a" wrap>{bug.description}</text>
                    <text size="xsmall" color="#a07850">{STATUS_LABELS[bug.status]}</text>
                  </vstack>
                </hstack>
              ))
            )}
          </vstack>

          {/* Roulette result */}
          {rouletteResult && (
            <vstack gap="small" padding="small" backgroundColor="#2a1f0e" cornerRadius="small">
              <text size="small" color="#a07850">Debug Roulette says:</text>
              <text size="medium" color="#e8c97a" weight="bold">{rouletteResult}</text>
            </vstack>
          )}

          {/* Divider */}
          <hstack width="100%" height="1px" backgroundColor="#3d2e1a" />

          {/* Action buttons */}
          <hstack gap="small">
            <button
              appearance="primary"
              grow
              onPress={() => context.ui.showForm(submitForm)}
            >
              Leave Something on the Table
            </button>
            <button
              appearance="secondary"
              onPress={() => setRouletteResult(pickNapkin())}
            >
              Spin 🎲
            </button>
          </hstack>
          <button
            appearance="plain"
            onPress={() => context.ui.showForm(updateForm)}
          >
            Update a Bug
          </button>
        </vstack>
      );
    },
  });
}

/**
 * Post a new Candlelit Corner to the subreddit.
 * Called by the weekly scheduler job.
 */
export async function postCandlelitCorner(context: TriggerContext): Promise<void> {
  try {
    const sub = await context.reddit.getCurrentSubreddit();
    const count = await getBugCount(context);

    const post = await context.reddit.submitPost({
      title: `The Candlelit Corner — ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}`,
      subredditName: sub.name,
      preview: (
        <vstack height="100%" width="100%" alignment="center middle" backgroundColor="#1a1209">
          <text color="white" size="large">THE CANDLELIT CORNER 🕯️</text>
          <text color="#a07850" size="small">
            {count === 0 ? 'Nothing on the table yet.' : `${count} things on the table.`}
          </text>
          <text color="#a07850" size="small">Loading the corner...</text>
        </vstack>
      ),
    });

    const comment = await context.reddit.submitComment({
      id: post.id,
      text: `The corner is lit. ${count > 0 ? `${count} things on the table.` : 'Nothing on the table yet.'} Bring your broken code and yourself.`,
    });

    try {
      await comment.distinguish(true);
    } catch (e) {
      logger.error('CandlelitCorner', 'distinguish failed', e);
    }

    logger.info('CandlelitCorner', `posted to r/${sub.name}: ${post.id}`);
  } catch (e) {
    logger.error('CandlelitCorner', 'postCandlelitCorner failed', e);
  }
}
