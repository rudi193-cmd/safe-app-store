/**
 * Gerald's logger. Ported from devvit/src/logger.ts — same shape so ops tooling
 * that greps for `[Module] message` across the llmphysics-bot and gerald-bot
 * logs continues to work.
 *
 * Set DEBUG_MODE to false before production deploy to silence the bot.
 */
const DEBUG_MODE = true;

export const logger = {
  info: (module: string, message: string) => {
    if (DEBUG_MODE) console.log(`[${module}] ${message}`);
  },
  error: (module: string, message: string, error?: unknown) => {
    if (DEBUG_MODE) console.error(`[${module}] ERROR: ${message}`, error || '');
  },
};
