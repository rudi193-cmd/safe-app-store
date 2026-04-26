/** @jsx Devvit.createElement */
/** @jsxFrag Devvit.Fragment */

import { Devvit, useState, useAsync, useForm } from '@devvit/public-api';
import type { TriggerContext } from '@devvit/public-api';
import { getDeltaSigma, getRecentGaps, addGap, formatDeltaSigma } from '../lib/gaps';
import { recordInteraction } from '../lib/flair';
import { logger } from '../lib/logger';

/**
 * The Observatory Log — Oakenscroll's interactive custom post type.
 *
 * Displays the ΔΣ gaps catalog. Users can submit observations.
 * Oakenscroll does not reduce the table. He only adds to it.
 *
 * Rendered as a Devvit Blocks custom post. Posted weekly on Monday.
 * Also pinnable by mods via menu item.
 */

export const POST_TYPE_NAME = 'Observatory Log';

export function registerObservatoryLog(): void {
  Devvit.addCustomPostType({
    name: POST_TYPE_NAME,
    description: "The Observatory is open. Acknowledged unknowns on file.",
    height: 'tall',
    render: (context) => {
      const [refreshKey, setRefreshKey] = useState(0);

      const { data: deltaData } = useAsync(
        async () => {
          const count = await getDeltaSigma(context);
          const gaps = await getRecentGaps(context, 5);
          return { count, gaps };
        },
        { depends: refreshKey },
      );

      const submissionForm = useForm(
        {
          title: 'Submit an Observation',
          description: 'What did you observe? What frame did you assume?',
          fields: [
            {
              type: 'string',
              name: 'observation',
              label: 'Observation',
              helpText: 'What did you observe? Be specific about the gap.',
              required: true,
            },
            {
              type: 'string',
              name: 'frame',
              label: 'Reference frame assumed (optional)',
              helpText: 'Leave blank if unknown. Oakenscroll will note the absence.',
              required: false,
            },
          ],
        },
        async (values) => {
          const observation = values.observation as string;
          const frame = values.frame as string | undefined;
          const username = (await context.reddit.getCurrentUser())?.username ?? 'unknown';
          const subreddit = (await context.reddit.getCurrentSubreddit()).name;

          const description = frame
            ? `${observation} [frame: ${frame}]`
            : `${observation} [frame: unspecified]`;

          await addGap(context, description, username);
          await recordInteraction(context, username, subreddit);
          context.ui.showToast({ text: 'Filed. The observatory notes this.' });
          setRefreshKey((k: number) => k + 1);
        },
      );

      const count = deltaData?.count ?? 0;
      const gaps = deltaData?.gaps ?? [];
      const dsLine = formatDeltaSigma(count);

      return (
        <vstack height="100%" width="100%" padding="medium" gap="medium" backgroundColor="#0d1117">
          {/* Header */}
          <vstack gap="small">
            <text size="xlarge" weight="bold" color="white">
              THE OBSERVATORY LOG
            </text>
            <text size="small" color="#8b949e">
              Department of Theoretical Uncertainty, UTETY
            </text>
            <text size="small" color="#58a6ff">
              {dsLine}
            </text>
          </vstack>

          {/* Divider */}
          <hstack width="100%" height="1px" backgroundColor="#30363d" />

          {/* Recent gaps */}
          <vstack gap="small" grow>
            <text size="medium" weight="bold" color="#c9d1d9">
              Recent Acknowledged Unknowns
            </text>
            {gaps.length === 0 ? (
              <text size="small" color="#8b949e">
                No observations on file. The table is empty.
              </text>
            ) : (
              gaps.map((gap, i) => (
                <hstack key={String(i)} gap="small" alignment="start top">
                  <text size="small" color="#58a6ff">•</text>
                  <text size="small" color="#c9d1d9" wrap>{gap.description}</text>
                </hstack>
              ))
            )}
          </vstack>

          {/* Divider */}
          <hstack width="100%" height="1px" backgroundColor="#30363d" />

          {/* Submit button */}
          <vstack gap="small">
            <text size="xsmall" color="#8b949e">
              The observatory is accepting observations. Knock twice.
            </text>
            <button
              appearance="primary"
              onPress={() => context.ui.showForm(submissionForm)}
            >
              Submit an Observation
            </button>
          </vstack>
        </vstack>
      );
    },
  });
}

/**
 * Post a new Observatory Log to the subreddit.
 * Called by the weekly scheduler job.
 */
export async function postObservatoryLog(context: TriggerContext): Promise<void> {
  try {
    const sub = await context.reddit.getCurrentSubreddit();
    const count = await getDeltaSigma(context);
    const dsLine = formatDeltaSigma(count);

    const post = await context.reddit.submitPost({
      title: `The Observatory Log — ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}`,
      subredditName: sub.name,
      preview: (
        <vstack height="100%" width="100%" alignment="center middle" backgroundColor="#0d1117">
          <text color="white" size="large">THE OBSERVATORY LOG</text>
          <text color="#8b949e" size="small">{dsLine}</text>
          <text color="#8b949e" size="small">Loading observations...</text>
        </vstack>
      ),
    });

    // Distinguished mod comment opens the log
    const comment = await context.reddit.submitComment({
      id: post.id,
      text: `The observatory is open. ${dsLine} Submit an observation above.`,
    });

    try {
      await comment.distinguish(true);
    } catch (e) {
      logger.error('ObservatoryLog', 'distinguish failed', e);
    }

    logger.info('ObservatoryLog', `posted to r/${sub.name}: ${post.id}`);
  } catch (e) {
    logger.error('ObservatoryLog', 'postObservatoryLog failed', e);
  }
}
