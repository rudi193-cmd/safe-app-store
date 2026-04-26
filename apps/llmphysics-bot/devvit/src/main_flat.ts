import { Devvit, SettingScope } from '@devvit/public-api';

Devvit.configure({ redditAPI: true, http: true, redis: true });

const BOT_USERNAME = 'llmphysics-bot';
const NEWSLETTER_JOB = 'mod_newsletter';
const HEARTBEAT_JOB = 'config_heartbeat';
const BLANK_NEWSLETTER = '_No entries this week._';

// --- Wikipedia Logic ---

async function lookupTerm(term: string) {
  const summaryUrl = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`;
  const res = await fetch(summaryUrl);
  if (!res.ok) return null;
  const data = await res.json() as any;
  
  // Basic science category filter check
  const catUrl = `https://en.wikipedia.org/w/api.php?action=query&prop=categories&titles=${encodeURIComponent(data.title)}&format=json&clshow=!hidden`;
  const catRes = await fetch(catUrl);
  const catData = await catRes.json() as any;
  const pages = catData.query?.pages || {};
  const categories = (Object.values(pages)[0] as any).categories || [];
  const isOffTopic = categories.every((c: any) => 
    /births|deaths|politicians|actors|films|songs|sports|companies/i.test(c.title)
  );

  return isOffTopic ? null : data;
}

// --- Newsletter Logic ---

async function runNewsletter(context: Devvit.Context) {
  const sub = (await context.reddit.getCurrentSubreddit()).name;
  const wikiPage = (await context.settings.get<string>('newsletterWikiPage')) || 'mod-newsletter';
  const postTitle = (await context.settings.get<string>('newsletterPostTitle')) || 'Weekly Mod Newsletter';

  try {
    const wiki = await context.reddit.getWikiPage(sub, wikiPage);
    const content = wiki.content.trim();
    if (!content || content === BLANK_NEWSLETTER) return;

    const post = await context.reddit.submitPost({ subredditName: sub, title: postTitle, text: content });
    await context.reddit.distinguish(post.id, true);
    await context.reddit.sticky(post.id, true);
    await context.reddit.updateWikiPage({ subredditName: sub, page: wikiPage, content: BLANK_NEWSLETTER });
  } catch (e) {
    console.error('Newsletter failed', e);
  }
}

// --- Settings ---

Devvit.addSettings([
  { name: 'newsletterWikiPage', label: 'Wiki Page', type: 'string', defaultValue: 'mod-newsletter' },
  { name: 'newsletterCron', label: 'Cron', type: 'string', defaultValue: '0 0 * * 0' },
  { name: 'newsletterPostTitle', label: 'Title', type: 'string', defaultValue: 'Weekly Mod Newsletter' },
  { name: 'summarySentences', label: 'Sentences', type: 'number', defaultValue: 3 },
]);

// --- Triggers ---

Devvit.addTrigger({
  event: 'CommentSubmit',
  onEvent: async (event, context) => {
    const body = event.comment?.body;
    if (!body || event.author?.name.toLowerCase() === BOT_USERNAME) return;

    const regex = new RegExp(`u/${BOT_USERNAME}\\b.*!define\\s+(.*)`, 'is');
    const match = body.match(regex);
    if (!match) return;

    const term = match[1].split(/[.?!,;\n]/)[0].trim();
    const data = await lookupTerm(term);
    if (!data) return;

    const sentences = (await context.settings.get<number>('summarySentences')) || 3;
    const extract = data.extract.split(/[.!?]\s/).slice(0, sentences).join('. ') + '.';
    
    await context.reddit.submitComment({
      id: event.comment.id,
      text: `**[${data.title}](${data.content_urls.desktop.page})**\n\n${extract}\n\n---\n^(*Summon: u/${BOT_USERNAME} !define <term>*)`
    });
  },
});

// --- Scheduler ---

Devvit.addSchedulerJob({ name: NEWSLETTER_JOB, onRun: async (_, context) => await runNewsletter(context) });

Devvit.addSchedulerJob({
  name: HEARTBEAT_JOB,
  onRun: async (_, context) => {
    const cron = (await context.settings.get<string>('newsletterCron')) || '0 0 * * 0';
    const lastCron = await context.redis.get('last_cron');
    if (cron !== lastCron) {
      const oldId = await context.redis.get('newsletter_job_id');
      if (oldId) await context.scheduler.cancel(oldId).catch(() => {});
      const newId = await context.scheduler.runJob({ cron, name: NEWSLETTER_JOB });
      await context.redis.set('newsletter_job_id', newId);
      await context.redis.set('last_cron', cron);
    }
  },
});

Devvit.addTrigger({
  event: 'AppInstall',
  onEvent: async (_, context) => {
    await context.scheduler.runJob({ cron: '*/5 * * * *', name: HEARTBEAT_JOB });
  },
});

export default Devvit;