// Version: 0.7.24
import { Devvit } from '@devvit/public-api';
import { logger } from './logger';

const BLANK_NEWSLETTER = '_No entries this week._';

export async function runNewsletter(
  context: Devvit.Context,
  subredditName: string,
  wikiPage: string,
  postTitle: string
): Promise<void> {
  try {
    const wiki = await context.reddit.getWikiPage(subredditName, wikiPage);
    const content = wiki.content.trim();

    if (!content || content === BLANK_NEWSLETTER) {
      logger.info('Newsletter', `Wiki page ${wikiPage} is empty. Skipping.`);
      return;
    }

    const post = await context.reddit.submitPost({
      subredditName,
      title: postTitle,
      text: content,
    });

    await context.reddit.distinguish(post.id, true);
    await context.reddit.sticky(post.id, true);

    await context.reddit.updateWikiPage({
      subredditName,
      page: wikiPage,
      content: BLANK_NEWSLETTER,
    });

    logger.info('Newsletter', `Posted ${post.id} and reset wiki.`);
  } catch (error) {
    logger.error('Newsletter', 'Execution failed', error);
  }
}