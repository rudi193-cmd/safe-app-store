/**
 * Hanz's logger. Same shape as gerald-bot/src/lib/logger.ts.
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
