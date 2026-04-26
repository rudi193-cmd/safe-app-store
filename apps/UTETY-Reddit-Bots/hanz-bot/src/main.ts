import { Devvit } from '@devvit/public-api';
import type { TriggerContext } from '@devvit/public-api';
import { logger } from './lib/logger';
import { handleNewPost } from './triggers/newPost';
import { handleDebuggingWitness } from './triggers/debuggingWitness';
import { handleSummon } from './triggers/summon';
import { pollScoreMilestones } from './triggers/scoreMilestone';
import { runNapkinDrop } from './triggers/napkinDrop';
import { registerCandlelitCorner, postCandlelitCorner } from './posts/candlelitCorner';

/**
 * Professor Hanz Christian Anderthon. Department of Code, UTETY.
 *
 * Can speak. Speaks with kindness. Bring your broken code and yourself.
 *
 * Trigger surface:
 *   PostSubmit    — code-shaped post observation (newPost) + stuck-ness detection (debuggingWitness)
 *   CommentSubmit — explicit summon via !hanz, !hanz bug, !hanz spin
 *
 * Scheduler jobs:
 *   heartbeat     — score milestone polling, every 10 min
 *   napkin_drop   — candlelit drop on recent post, every 6h (probabilistic)
 *   weekly_corner — Candlelit Corner custom post, every Sunday 20:00 UTC
 *
 * Custom post type:
 *   Candlelit Corner — interactive Known Bugs Registry + Debug Roulette
 *
 * Menu items:
 *   Post Candlelit Corner Now (mod-only)
 *   View Known Bugs Count (mod-only)
 */

Devvit.configure({ redditAPI: true, redis: true });

// ---- Custom Post Type ----
registerCandlelitCorner();

// ---- Scheduler job names ----
const HEARTBEAT_JOB = 'hanz_heartbeat';
const NAPKIN_JOB = 'hanz_napkin_drop';
const WEEKLY_CORNER_JOB = 'hanz_weekly_corner';

// ---- Triggers ----
Devvit.addTrigger({
  event: 'PostSubmit',
  onEvent: async (event, context) => {
    try {
      await handleNewPost(context, event);
      await handleDebuggingWitness(context, event);
    } catch (e) {
      logger.error('Trigger:PostSubmit', 'unhandled', e);
    }
  },
});

Devvit.addTrigger({
  event: 'CommentSubmit',
  onEvent: async (event, context) => {
    try {
      await handleSummon(context, event);
    } catch (e) {
      logger.error('Trigger:CommentSubmit', 'unhandled', e);
    }
  },
});

// ---- Scheduler jobs ----
Devvit.addSchedulerJob({
  name: HEARTBEAT_JOB,
  onRun: async (_, context) => {
    try {
      await pollScoreMilestones(context);
    } catch (e) {
      logger.error('Heartbeat', 'failed', e);
    }
  },
});

Devvit.addSchedulerJob({
  name: NAPKIN_JOB,
  onRun: async (_, context) => {
    try {
      await runNapkinDrop(context);
    } catch (e) {
      logger.error('NapkinJob', 'failed', e);
    }
  },
});

Devvit.addSchedulerJob({
  name: WEEKLY_CORNER_JOB,
  onRun: async (_, context) => {
    try {
      await postCandlelitCorner(context);
    } catch (e) {
      logger.error('WeeklyCorner', 'failed', e);
    }
  },
});

// ---- Menu items (mod-only) ----
Devvit.addMenuItem({
  label: 'Post Candlelit Corner Now',
  location: 'subreddit',
  forUserType: 'moderator',
  onPress: async (_, context) => {
    await postCandlelitCorner(context);
    context.ui.showToast({ text: 'Candlelit Corner posted. The candle is on.' });
  },
});

Devvit.addMenuItem({
  label: 'View Known Bugs Count',
  location: 'subreddit',
  forUserType: 'moderator',
  onPress: async (_, context) => {
    const { getBugCount } = await import('./lib/bugs');
    const count = await getBugCount(context);
    context.ui.showToast({
      text: count === 0
        ? 'No bugs on the table.'
        : `${count} bug${count === 1 ? '' : 's'} on the table.`,
    });
  },
});

// ---- Install / upgrade ----
async function fullReboot(context: TriggerContext): Promise<void> {
  try {
    const jobs = await context.scheduler.listJobs();
    for (const job of jobs) {
      try { await context.scheduler.cancelJob(job.id); } catch { /* ignore */ }
    }
  } catch (e) {
    logger.error('Reboot', 'listJobs failed', e);
  }

  await context.scheduler.runJob({ cron: '*/10 * * * *', name: HEARTBEAT_JOB });
  await context.scheduler.runJob({ cron: '0 */6 * * *', name: NAPKIN_JOB });
  await context.scheduler.runJob({ cron: '0 20 * * 0', name: WEEKLY_CORNER_JOB }); // Sunday 20:00 UTC

  logger.info('Reboot', 'Hanz is at the candlelit corner. The candle is on.');
}

Devvit.addTrigger({ event: 'AppInstall', onEvent: async (_, context) => await fullReboot(context) });
Devvit.addTrigger({ event: 'AppUpgrade', onEvent: async (_, context) => await fullReboot(context) });

export default Devvit;
