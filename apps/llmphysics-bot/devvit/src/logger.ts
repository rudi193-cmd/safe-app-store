// Version: 0.7.24
/**
 * Global logging toggle. 
 * Set to false before publishing to silence all bot logs.
 */
const DEBUG_MODE = true;

export const logger = {
  info: (module: string, message: string) => {
    if (DEBUG_MODE) console.log(`[${module}] ${message}`);
  },
  error: (module: string, message: string, error?: any) => {
    if (DEBUG_MODE) console.error(`[${module}] ERROR: ${message}`, error || '');
  }
};