// Version: 0.7.25
import { Devvit } from '@devvit/public-api';
import { logger } from './logger';

export const NEWSLETTER_JOB = 'mod_newsletter';
export const HEARTBEAT_JOB = 'config_heartbeat';
const OLD_HEARTBEAT_JOB = 'heartbeat'; // Ghost job name to clean up

const NEWSLETTER_JOB_ID_KEY = 'newsletter_job_id';
const LAST_CRON_KEY = 'last_cron';

export async function ensureNewsletterScheduled(context: Devvit.Context): Promise<void> {
  const cron = (await context.settings.get<string>('newsletterCron')) || '0 0 * * 0';
  const lastCron = await context.redis.get(LAST_CRON_KEY);

  if (cron === lastCron) return;

  const oldJobId = await context.redis.get(NEWSLETTER_JOB_ID_KEY);
  if (oldJobId) {
    try {
      await context.scheduler.cancel(oldJobId);
    } catch { /* ignore */ }
  }

  const newJobId = await context.scheduler.runJob({ cron, name: NEWSLETTER_JOB });
  await context.redis.set(NEWSLETTER_JOB_ID_KEY, newJobId);
  await context.redis.set(LAST_CRON_KEY, cron);
  logger.info('Heartbeat', `Newsletter scheduled: ${newJobId}`);
}

/**
 * Specifically targets and cancels the old job name to stop "Job not found" errors.
 */
export async function cleanOldJobs(context: Devvit.Context): Promise<void> {
  try {
    const jobs = await context.scheduler.listJobs();
    const ghost = jobs.find(j => j.name === OLD_HEARTBEAT_JOB);
    if (ghost) {
      await context.scheduler.cancel(ghost.id);
      logger.info('Heartbeat', `Cleaned up legacy job: ${OLD_HEARTBEAT_JOB}`);
    }
  } catch (e) {
    // Fail silently if listJobs is unavailable or errors
  }
}

export async function onHeartbeat(context: Devvit.Context): Promise<void> {
  try {
    await ensureNewsletterScheduled(context);
  } catch (e) {
    logger.error('Heartbeat', 'Heartbeat failed', e);
  }
}