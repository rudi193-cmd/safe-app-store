// Version: 0.7.24
export interface ParseResult {
  command: string;
  payload: string;
}

/**
 * Identifies the command and payload from a comment.
 */
export async function routeComment(
  event: any,
  botUsername: string,
  availableCommands: string[]
): Promise<ParseResult | null> {
  const body = event.comment?.body;
  if (!body || !event.author) return null;
  if (event.author.name.toLowerCase() === botUsername) return null;

  for (const cmd of availableCommands) {
    const regex = new RegExp(`u/${botUsername}\\b.*${cmd}\\s+(.*)`, 'is');
    const match = body.match(regex);
    
    if (match) {
      const payload = match[1].split(/[.?!,;\n]/)[0].trim();
      if (payload) return { command: cmd, payload };
    }
  }

  return null;
}