import { Devvit } from '@devvit/public-api';
import type { TriggerContext } from '@devvit/public-api';
import { logger } from './lib/logger';
import { handleNewPost } from './triggers/newPost';
import { handleRefFrame } from './triggers/refFrame';
import { handleSummon } from './triggers/summon';
import { pollScoreMilestones } from './triggers/scoreMilestone';
import { runNapkinDrop } from './triggers/napkinDrop';
import { registerObservatoryLog, postObservatoryLog } from './posts/observatoryLog';

/**
 * Professor Oakenscroll. Department of Theoretical Uncertainty, UTETY.
 *
 * Can speak. Rarely does. When he does, it is a reframing, not an answer.
 *
 * Trigger surface:
 *   PostSubmit    — domain post observation (newPost) + reference frame detection (refFrame)
 *   CommentSubmit — explicit summon via !oak, !oak gap, !oak frame
 *
 * Scheduler jobs:
 *   heartbeat     — score milestone polling, every 10 min
 *   napkin_drop   — cryptic drop on recent post, every 6h (probabilistic)
 *   weekly_log    — Observatory Log custom post, every Monday 09:00 UTC
 *
 * Custom post type:
 *   Observatory Log — interactive ΔΣ gaps catalog with submission form
 *
 * Menu items:
 *   Post Observatory Log (mod-only, available on subreddit)
 */

Devvit.configure({ redditAPI: true, redis: true });

// ---- Custom Post Type ----
registerObservatoryLog();

// ---- Scheduler job names ----
const HEARTBEAT_JOB = 'oakenscroll_heartbeat';
const NAPKIN_JOB = 'oakenscroll_napkin_drop';
const WEEKLY_LOG_JOB = 'oakenscroll_weekly_log';

// ---- Triggers ----
Devvit.addTrigger({
  event: 'PostSubmit',
  onEvent: async (event, context) => {
    try {
      await handleNewPost(context, event);
      await handleRefFrame(context, event);
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
  name: WEEKLY_LOG_JOB,
  onRun: async (_, context) => {
    try {
      await postObservatoryLog(context);
    } catch (e) {
      logger.error('WeeklyLog', 'failed', e);
    }
  },
});

// ---- Menu items (mod-only) ----
Devvit.addMenuItem({
  label: 'Post Observatory Log Now',
  location: 'subreddit',
  forUserType: 'moderator',
  onPress: async (_, context) => {
    await postObservatoryLog(context);
    context.ui.showToast({ text: 'Observatory Log posted.' });
  },
});

Devvit.addMenuItem({
  label: "View ΔΣ Status",
  location: 'subreddit',
  forUserType: 'moderator',
  onPress: async (_, context) => {
    const { getDeltaSigma, formatDeltaSigma } = await import('./lib/gaps');
    const count = await getDeltaSigma(context);
    context.ui.showToast({ text: formatDeltaSigma(count) });
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
  await context.scheduler.runJob({ cron: '0 9 * * 1', name: WEEKLY_LOG_JOB }); // Monday 09:00 UTC

  logger.info('Reboot', 'Oakenscroll is available. The observatory is unlocked.');
}

Devvit.addTrigger({ event: 'AppInstall', onEvent: async (_, context) => await fullReboot(context) });
Devvit.addTrigger({ event: 'AppUpgrade', onEvent: async (_, context) => await fullReboot(context) });

export default Devvit;
