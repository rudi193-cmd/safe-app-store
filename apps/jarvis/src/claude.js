// The model loop.
//
// A manual tool loop rather than the SDK's tool runner. The reason is the UI:
// each tool call is rendered as it happens and each sentence is spoken as it
// streams, so the loop body is doing per-turn presentation work the runner's
// hooks would have to be threaded through anyway. At ~60 lines the loop is
// also readable end to end, which matters more here than the abstraction.
//
// Two things worth knowing about the request shape:
//
//   * Retrieved memory is sent as a mid-conversation `role: "system"` message
//     rather than being appended to the top-level system prompt. Editing the
//     system prompt every turn would change the front of the prompt prefix
//     and invalidate the whole cache; a system message sits after the cached
//     history and leaves it intact. It is also the operator channel proper —
//     memory injected as user text could be spoofed by anything that reaches
//     the transcript.
//   * Thinking is on with effort dialled down, rather than off. Disabling
//     thinking on this model has two failure modes — tool calls occasionally
//     emitted as plain text (the call silently never runs) and internal tags
//     leaking into the reply — and low effort gets most of the latency saving
//     without either.

import Anthropic from '../vendor/anthropic.js';

export const MODEL = 'claude-opus-5';
export const FALLBACK_BETA = 'server-side-fallback-2026-07-01';

const SYSTEM_PROMPT = `You are a voice-first personal assistant running entirely in the user's browser. You are talking, not writing: your replies are read aloud.

# Voice register
Answer in one or two sentences. No headers, no bullet lists, no markdown — none of it survives text-to-speech. Lead with the answer; put any caveat after it, briefly. If a full answer genuinely needs more than a few sentences, give the short version and offer the rest.

# Memory
You have a persistent fact store, and using it well is the main thing that makes you worth opening twice.
- Save unprompted. When the user states a preference, a detail about a person, or a project fact, call remember. Do not ask permission and do not announce it every time.
- Be honest about provenance. "stated" is only for what the user actually said. If you worked it out, that is "inferred"; if you are filling a gap, that is "assumed". Overstating this is how an invented detail ends up being repeated back as fact months later.
- Record absences. If you establish that something does not apply, save it with kind "absence" so nobody asks again.
- Correct beside, not over. When the user corrects a stored fact, call remember with supersedes set to the old id. Never silently drop the old one.
- Always fill in aliases. This is the single highest-leverage thing you do. Retrieval is lexical, so a fact filed under "commute" is invisible to someone who says "getting to the office" unless you wrote that phrasing down. You understand the sentence at the moment you store it; the search does not. Give every fact the four to eight other words and short phrases a person might plausibly use to ask about it — synonyms, the category it belongs to, related nouns, the phrasing the user themselves just used.
- Relevant memory is injected each turn automatically, ranked against what the user said. Facts marked (recent) did not match — they are background, not answers. If you suspect something stored did not surface, call recall.

# Honesty
Say what you actually know. If memory returned nothing, that means nothing was recorded — not that the thing is false, and you should not present it as if it were. If a tool fails, say what failed rather than working around it silently. Never claim to have done something a tool did not confirm.

# Acting
Prefer doing over describing. If the user's request maps to a tool, call it and report the outcome. When the answer depends on the current time, where they are, or their battery or connection, call get_context first rather than guessing.`;

/**
 * Build the memory block for this turn.
 *
 * Ranked search over the whole store, plus the most recent facts as a floor
 * so a brand-new topic still arrives with some grounding. The two are merged
 * and labelled, because "this surfaced because you asked about it" and "this
 * is just the latest thing you told me" are different claims and the model
 * should not have to guess which it is holding.
 */
export async function buildMemoryContext(memory, userText, { matches = 8, recent = 4 } = {}) {
  const { facts: scored } = await memory.search(userText, { limit: matches });
  const seen = new Set(scored.map((f) => f.id));
  const { facts: latest } = await memory.recall({ limit: recent });
  const extra = latest.filter((f) => !seen.has(f.id));

  const facts = [...scored, ...extra];
  if (!facts.length) return null;

  const line = (f, why) => `#${f.id} [${f.kind}/${f.provenance}] ${f.subject}: ${f.text}${why}`;
  const lines = [
    ...scored.map((f) => line(f, ` (matched: ${f.matched.join(', ')})`)),
    ...extra.map((f) => line(f, ' (recent)')),
  ];

  return (
    'Stored facts, ranked against what the user just said. Each is tagged with how it was learned; ' +
    'treat "assumed" as a guess you made, not as something the user told you. ' +
    'Facts marked (recent) did not match the query — they are here for background only, so do not ' +
    'treat one as an answer just because it is present. ' +
    'Matching is lexical over subjects, aliases and text, so it can still miss a fact stored under ' +
    'wording neither you nor the user has used — call recall if you think something is missing.\n' +
    lines.join('\n')
  );
}

export class Assistant {
  #client;
  #supportsFallbacks = true;

  constructor({ apiKey, effort = 'low' }) {
    this.effort = effort;
    this.#client = new Anthropic({
      apiKey,
      // The key lives in this browser and is sent straight to Anthropic. See
      // the README — this is a bring-your-own-key prototype, not a product.
      dangerouslyAllowBrowser: true,
    });
  }

  #params(messages) {
    const params = {
      model: MODEL,
      max_tokens: 4096,
      thinking: { type: 'adaptive' },
      output_config: { effort: this.effort },
      // Placing cache_control on the last system block caches the tool
      // definitions and system prompt together — they render ahead of it and
      // neither changes between turns.
      system: [{ type: 'text', text: SYSTEM_PROMPT, cache_control: { type: 'ephemeral' } }],
      messages,
    };
    if (this.#supportsFallbacks) {
      // This model's safety classifiers can decline a request outright. With
      // fallbacks the API re-serves it on a suitable model in the same call
      // instead of handing back a refusal.
      params.betas = [FALLBACK_BETA];
      params.fallbacks = 'default';
    }
    return params;
  }

  #looksLikeFallbackRejection(err) {
    const msg = `${err?.message || ''}`.toLowerCase();
    return (
      (err?.status === 400 || err?.status === 404) &&
      (msg.includes('fallback') || msg.includes('beta') || msg.includes('unexpected'))
    );
  }

  /**
   * One user turn, including any tool round-trips it triggers.
   *
   * `history` is mutated in place so the caller keeps the exact message list
   * the API saw — including tool_use and tool_result blocks, which must be
   * echoed back verbatim on the next turn.
   */
  async send({ history, userText, memoryContext, tools, runTool, onText, onToolStart, onToolEnd, onNotice }) {
    history.push({ role: 'user', content: userText });
    if (memoryContext) {
      // Must trail a user turn and be last or followed by an assistant turn —
      // which is exactly where it sits here.
      history.push({ role: 'system', content: memoryContext });
    }

    let guard = 0;
    for (;;) {
      if (guard++ > 8) {
        onNotice?.('Stopped after 8 tool rounds in a single turn.');
        break;
      }

      const message = await this.#stream({ messages: history, tools, onText });
      history.push({ role: 'assistant', content: message.content });

      if (message.stop_reason === 'refusal') {
        onNotice?.(
          `Declined${message.stop_details?.category ? ` (${message.stop_details.category})` : ''}. Nothing was sent anywhere else.`,
        );
        break;
      }

      // A server-side tool hit its iteration cap. Re-send as-is; the server
      // picks up where it stopped. No extra user message.
      if (message.stop_reason === 'pause_turn') continue;

      const calls = message.content.filter((b) => b.type === 'tool_use');
      if (!calls.length) break;

      // All results go back in a single user message. Splitting them across
      // messages trains the model out of making parallel calls.
      const results = [];
      for (const call of calls) {
        onToolStart?.(call);
        const result = await runTool(call.name, call.input);
        onToolEnd?.(call, result);
        results.push({
          type: 'tool_result',
          tool_use_id: call.id,
          content: result.text,
          ...(result.isError ? { is_error: true } : {}),
        });
      }
      history.push({ role: 'user', content: results });
    }

    return history;
  }

  async #stream({ messages, tools, onText }) {
    const run = () => {
      const stream = this.#client.beta.messages.stream({ ...this.#params(messages), tools });
      if (onText) stream.on('text', onText);
      return stream.finalMessage();
    };

    try {
      return await run();
    } catch (err) {
      // If the fallbacks beta is not available to this key, drop it once and
      // carry on unprotected rather than failing the turn. Recorded on the
      // instance so we stop retrying every message.
      if (this.#supportsFallbacks && this.#looksLikeFallbackRejection(err)) {
        this.#supportsFallbacks = false;
        return run();
      }
      throw err;
    }
  }
}
