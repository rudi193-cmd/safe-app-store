// Version: 0.7.34
import { Devvit, SettingScope } from '@devvit/public-api';
import { routeComment } from './parsing';
import { runNewsletter } from './newsletter';
import { HEARTBEAT_JOB, NEWSLETTER_JOB, onHeartbeat, ensureNewsletterScheduled } from './heartbeat';
import { lookupTerm } from './lookup';
import { logger } from './logger';

Devvit.configure({ redditAPI: true, http: true, redis: true });

const BOT_USERNAME = 'llmphysics-bot';

/**
 * Multi-tier rate limiting logic
 * Returns: 0 (Normal), 1 (Warn), 2 (Timeout/Block)
 */
async function getSpamStatus(context: Devvit.Context, username: string, isMod: boolean): Promise<number> {
  if (isMod) return 0;

  const windowKey = `spam_window:${username}`;
  const timeoutKey = `spam_timeout:${username}`;

  const isTimedOut = await context.redis.get(timeoutKey);
  if (isTimedOut) return 2;

  // Use camelCase incrBy for Devvit API
  const count = await context.redis.incrBy(windowKey, 1);
  if (count === 1) {
    // Set 5 minute expiration for the window
    await context.redis.expire(windowKey, 300);
  }

  if (count >= 4) {
    // 30 minute timeout
    await context.redis.set(timeoutKey, 'true', { expiration: new Date(Date.now() + 1800000) });
    return 2;
  }
  
  return count === 3 ? 1 : 0;
}

const ACTIONS: Record<string, (context: Devvit.Context, event: any, payload: string, isMod: boolean) => Promise<void>> = {
  '!define': async (context, event, payload, isMod) => {
    const author = event.author?.name ?? 'unknown';
    const status = await getSpamStatus(context, author, isMod);

    if (status === 2) {
      await context.reddit.report(event.comment.id, { reason: "Spamming the bot" });
      await context.reddit.submitComment({ 
        id: event.comment.id, 
        text: `> I'm going to have to time you out for a half hour.` 
      });
      return;
    }

    const result = await lookupTerm(payload);
    if (!result) return;
    
    const sentences = (await context.settings.get<number>('summarySentences')) || 3;
    const summaryLines = result.summary.extract.split(/[.!?]\s/).slice(0, sentences);
    const summary = summaryLines.join('. ') + (summaryLines.length > 0 ? '.' : '');
    
    const prefix = status === 1 ? "> I'm a very busy bot, please don't spam me.\n\n" : "";

    const reply = `${prefix}**[${result.summary.title}](${result.summary.content_urls.desktop.page})**\n\n${summary}\n\n---\n\n^(*I am a bot for r/LLMPhysics. Summon me with \`u/${BOT_USERNAME} !define <term>\`*)`;

    await context.reddit.submitComment({ id: event.comment.id, text: reply });
  },
};

Devvit.addSettings([
  { name: 'blockedTerms', label: 'Blocked terms', type: 'string', scope: SettingScope.Installation },
  { name: 'newsletterWikiPage', label: 'Newsletter Wiki', type: 'string', scope: SettingScope.Installation, defaultValue: 'mod-newsletter' },
  { name: 'newsletterCron', label: 'Newsletter Cron', type: 'string', scope: SettingScope.Installation, defaultValue: '0 0 * * 0' },
  { name: 'newsletterPostTitle', label: 'Newsletter Title', type: 'string', scope: SettingScope.Installation, defaultValue: 'Weekly Mod Newsletter' },
  { name: 'summarySentences', label: 'Summary Length', type: 'number', scope: SettingScope.Installation, defaultValue: 3 },
]);

Devvit.addTrigger({
  event: 'CommentSubmit',
  onEvent: async (event, context) => {
    const intent = await routeComment(event, BOT_USERNAME, Object.keys(ACTIONS));
    if (intent) {
      const author = event.author?.name ?? 'unknown';
      const subreddit = event.subreddit?.name ?? 'unknown';
      const postId = event.post?.id ?? 'unknown';
      
      const moderators = await context.reddit.getModerators({ subredditName: subreddit }).all();
      const isMod = moderators.some(m => m.name === author);

      logger.info('Trigger:CommentSubmit', `[u/${author}${isMod ? ' (Mod)' : ''} @ r/${subreddit}] Intent: ${intent.command} on ${postId}`);
      
      if (ACTIONS[intent.command]) {
        await ACTIONS[intent.command](context, event, intent.payload, isMod);
      }
    }
  },
});

Devvit.addSchedulerJob({
  name: NEWSLETTER_JOB,
  onRun: async (_, context) => {
    const sub = await context.reddit.getCurrentSubreddit();
    const wiki = (await context.settings.get<string>('newsletterWikiPage')) || 'mod-newsletter';
    const title = (await context.settings.get<string>('newsletterPostTitle')) || 'Weekly Mod Newsletter';
    await runNewsletter(context, sub.name, wiki, title);
  },
});

Devvit.addSchedulerJob({ 
  name: HEARTBEAT_JOB, 
  onRun: async (_, context) => await onHeartbeat(context) 
});

async function fullReboot(context: Devvit.Context) {
  try {
    const jobs = await context.scheduler.listJobs();
    for (const job of jobs) await context.scheduler.cancel(job.id);
  } catch (e) {
    logger.error('System', 'Reboot failed', e);
  }
  await context.redis.del('last_cron');
  await context.redis.del('newsletter_job_id');
  await context.scheduler.runJob({ cron: '*/5 * * * *', name: HEARTBEAT_JOB });
  await ensureNewsletterScheduled(context);
}

Devvit.addTrigger({ event: 'AppInstall', onEvent: async (_, context) => await fullReboot(context) });
Devvit.addTrigger({ event: 'AppUpgrade', onEvent: async (_, context) => await fullReboot(context) });

export default Devvit;