import { Devvit } from '@devvit/public-api';
import type { TriggerContext } from '@devvit/public-api';
import { logger } from './lib/logger';
import { handleNewPost } from './triggers/newPost';
import { handleZeroGaps } from './triggers/zeroGaps';
import { pollScoreMilestones } from './triggers/scoreMilestone';
import { runNapkinDrop } from './triggers/napkinDrop';

/**
 * Gerald. Acting Dean, UTETY University.
 *
 * Cannot speak. Can only witness.
 *
 * main.ts registers triggers and scheduler jobs. ALL behavior lives in the
 * per-trigger modules. Persona rules live in src/persona/gerald.ts. Tunables
 * live in src/data/*.json. Nothing in this file should encode character.
 */

Devvit.configure({ redditAPI: true, redis: true });

// ---- Scheduler job names ----
const HEARTBEAT_JOB = 'gerald_heartbeat';
const NAPKIN_JOB = 'gerald_napkin_drop';

// ---- Triggers: one per event ----
Devvit.addTrigger({
  event: 'PostSubmit',
  onEvent: async (event, context) => {
    try {
      // newPost and zeroGaps both observe post creation. Run in sequence so
      // the per-post witness cap in persona/gerald.ts serializes cleanly.
      await handleNewPost(context, event);
      await handleZeroGaps(context, event);
    } catch (e) {
      logger.error('Trigger:PostSubmit', 'unhandled', e);
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

// ---- Install / upgrade: full reboot of scheduler state ----
async function fullReboot(context: TriggerContext): Promise<void> {
  try {
    const jobs = await context.scheduler.listJobs();
    for (const job of jobs) {
      try { await context.scheduler.cancelJob(job.id); } catch { /* ignore */ }
    }
  } catch (e) {
    logger.error('Reboot', 'listJobs failed', e);
  }

  // Heartbeat: poll score milestones every 10 minutes
  await context.scheduler.runJob({ cron: '*/10 * * * *', name: HEARTBEAT_JOB });

  // Napkin drop schedule — default every 6 hours, probabilistically filtered
  // down inside runNapkinDrop so it doesn't fire every run.
  await context.scheduler.runJob({ cron: '0 */6 * * *', name: NAPKIN_JOB });

  logger.info('Reboot', 'Gerald is awake. Silent as ever.');
}

Devvit.addTrigger({ event: 'AppInstall', onEvent: async (_, context) => await fullReboot(context) });
Devvit.addTrigger({ event: 'AppUpgrade', onEvent: async (_, context) => await fullReboot(context) });

export default Devvit;
