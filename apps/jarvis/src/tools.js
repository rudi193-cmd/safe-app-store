// Tool definitions and their handlers.
//
// These are client-executed tools: the model emits a tool_use block, this
// file runs it against local state, and the result goes back. Nothing here
// leaves the device except the tool_result text the model then reads.
//
// Descriptions are prescriptive about *when* to call, not just what the tool
// does. Recent Opus models reach for tools conservatively, and a description
// that only states a capability measurably under-triggers compared to one
// that states a trigger condition.

export const TOOL_DEFS = [
  {
    name: 'remember',
    description:
      'Store a durable fact about the user. Call this whenever the user states a preference, a personal detail, a relationship, or a project fact that would be useful in a future conversation — do not wait to be asked to remember. Also call it with kind="absence" when you establish that something does NOT apply (e.g. the user has no dietary restrictions); a recorded absence is different from having no record, and prevents asking the same question twice.',
    input_schema: {
      type: 'object',
      properties: {
        subject: {
          type: 'string',
          description:
            'Short lookup key, 1-3 words, lowercase — e.g. "coffee", "sister", "commute". This is the index key used to retrieve the fact later, so prefer the noun the user would use.',
        },
        kind: {
          type: 'string',
          enum: ['fact', 'preference', 'person', 'project', 'absence'],
          description: 'Use "absence" to record that something does not apply.',
        },
        text: { type: 'string', description: 'The fact, in one sentence, written so it makes sense months later.' },
        provenance: {
          type: 'string',
          enum: ['stated', 'inferred', 'assumed'],
          description:
            'How you know. "stated" only if the user said it outright; "inferred" if you concluded it from what they said; "assumed" if you are filling a gap. Be honest — this is not a confidence score, it is whether the claim traces back to something the user can check.',
        },
        aliases: {
          type: 'array',
          items: { type: 'string' },
          description:
            'Four to eight other words or short phrases someone might use when asking about this. Retrieval is lexical, so these are what make the fact findable under wording other than the subject — for subject "commute" give things like "office", "work", "getting to work", "travel". Include the phrasing the user just used. Skipping this is the main way a stored fact becomes unreachable.',
        },
        supersedes: {
          type: 'integer',
          description:
            'The id of a fact this replaces, when the user corrects something. The old fact is kept in history and stops appearing in recalls.',
        },
      },
      required: ['subject', 'kind', 'text', 'provenance'],
    },
  },
  {
    name: 'recall',
    description:
      'Look up stored facts. Call this when the user refers to something you may have been told before, asks what you know, or when answering would be materially better with prior context. Ranked memory is already injected each turn, so use this when that was not enough — try `query` with different wording than the user used, since matching is lexical and your rephrasing may hit an alias theirs did not.',
    input_schema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description:
            'Free text, ranked across subjects, aliases and body text. Prefer this over `subject` unless you know the exact key. Rephrasing is the point — if "commute" found nothing, try "office travel work".',
        },
        subject: { type: 'string', description: 'Exact lookup key. Use only when you know it, e.g. from an earlier result.' },
        kind: { type: 'string', enum: ['fact', 'preference', 'person', 'project', 'absence'] },
        limit: { type: 'integer', description: 'Max facts to return. Defaults to 20.' },
      },
    },
  },
  {
    name: 'forget',
    description:
      'Retire a fact so it stops appearing in recalls. Call this when the user asks you to forget something or says a stored fact is wrong and gives no replacement. The record itself is kept in history; only its live status changes.',
    input_schema: {
      type: 'object',
      properties: { id: { type: 'integer', description: 'The fact id, as returned by recall.' } },
      required: ['id'],
    },
  },
  {
    name: 'set_reminder',
    description:
      'Schedule a reminder. Call this when the user asks to be reminded, or agrees to a follow-up at a specific time. The tool result states whether the reminder survives the app being closed — repeat what it says when confirming, and never promise more reach than it reports.',
    input_schema: {
      type: 'object',
      properties: {
        in_minutes: { type: 'number', description: 'Minutes from now. Use this for relative times.' },
        at_iso: { type: 'string', description: 'Absolute ISO 8601 timestamp. Use this for a named clock time.' },
        text: { type: 'string', description: 'What to say when it fires.' },
      },
      required: ['text'],
    },
  },
  {
    name: 'list_reminders',
    description: 'List reminders that have not fired yet. Call this when the user asks what is scheduled.',
    input_schema: { type: 'object', properties: {} },
  },
  {
    name: 'get_context',
    description:
      'Read the device situation: current local time and timezone, network status, battery, and (only if the user has granted it) coarse location. Call this before any answer that depends on the current time, on where the user is, or on whether they are about to lose power or signal.',
    input_schema: {
      type: 'object',
      properties: {
        include_location: {
          type: 'boolean',
          description:
            'Request coarse location. This triggers a browser permission prompt the first time. Only set true when location actually changes the answer.',
        },
      },
    },
  },
  {
    name: 'willow_whoami',
    description:
      'Report the fleet identity this session is signed in as: the resolved app_id, permissions, and whether this is the human-only orchestrator seat. Call this when the user asks what account Jarvis is connected as, or before any other willow_ tool call if you are not sure the connection is live. If not signed in, the result says so — that is not an error to route around.',
    input_schema: { type: 'object', properties: {} },
  },
  {
    name: 'willow_dispatch_list',
    description:
      'List fleet dispatch packets (work assigned between agents), newest first. Call this when the user asks what work is in flight, what is pending, or what a given agent is working on. Read-only.',
    input_schema: {
      type: 'object',
      properties: {
        to_app: { type: 'string', description: 'Filter to packets assigned to this agent. Omit for no filter.' },
        from_app: { type: 'string', description: 'Filter to packets sent by this agent. Omit for no filter.' },
        status: { type: 'string', description: 'Filter by status, e.g. "pending", "working", "complete". Omit for no filter.' },
        limit: { type: 'integer', description: 'Max packets to return. Defaults to 20.' },
      },
    },
  },
  {
    name: 'willow_dispatch_read',
    description:
      'Read one dispatch packet in full: who assigned it, to whom, its phase and priority, current status, and the complete assignment brief. Call this when the user asks about a specific dispatch by id, or after willow_dispatch_list surfaces one worth reading in full. Read-only.',
    input_schema: {
      type: 'object',
      properties: { dispatch_id: { type: 'string', description: 'The dispatch packet id, as returned by willow_dispatch_list.' } },
      required: ['dispatch_id'],
    },
  },
  {
    name: 'willow_verify_handoff',
    description:
      'Check a completed dispatch\'s handoff: whether its closeout exists and its declarations actually hold (checklist resolved, envelope clean, findings present). Call this when the user asks whether an agent\'s work is actually done, before considering willow_agent_clear. Read-only — it checks, it does not release anything.',
    input_schema: {
      type: 'object',
      properties: { dispatch_id: { type: 'string', description: 'The dispatch packet id to verify.' } },
      required: ['dispatch_id'],
    },
  },
  {
    name: 'willow_dispatch_send',
    description:
      'Assign a work packet to another agent in the fleet. This is a write against the orchestrator seat — call it only when the user has explicitly directed you to send this specific assignment, never on your own initiative. willow-mcp gates who may actually complete this: if this session is not bound to the human-orchestrator identity, expect and report the denial rather than retrying.',
    input_schema: {
      type: 'object',
      properties: {
        to_app: { type: 'string', description: 'The agent this work is assigned to.' },
        assignment_md: { type: 'string', description: 'The full assignment brief the specialist will read, in markdown.' },
        role: { type: 'string', description: 'The role the specialist should take for this packet, if the fleet distinguishes one.' },
        summary: { type: 'string', description: 'One-line summary of the assignment, for listings.' },
        phase: { type: 'string', description: 'Defaults to "operate" if omitted.' },
        priority: { type: 'string', description: 'Defaults to "normal" if omitted.' },
      },
      required: ['to_app', 'assignment_md'],
    },
  },
  {
    name: 'willow_agent_clear',
    description:
      'Release a specialist agent after its handoff has been verified, clearing it for its next packet. This is a write against the orchestrator seat — call it only when the user has explicitly asked to clear this specific agent for this specific dispatch, and only after willow_verify_handoff, never on your own judgement that work "looks done". willow-mcp gates who may actually complete this and will report a denial rather than a fabricated success if this session lacks the standing.',
    input_schema: {
      type: 'object',
      properties: {
        target_app: { type: 'string', description: 'The agent being cleared.' },
        dispatch_id: { type: 'string', description: 'The dispatch packet id being closed out.' },
      },
      required: ['target_app', 'dispatch_id'],
    },
  },
];

/** Tool names whose results should never be spoken aloud verbatim. */
export const QUIET_TOOLS = new Set([
  'recall',
  'list_reminders',
  'get_context',
  'willow_whoami',
  'willow_dispatch_list',
  'willow_dispatch_read',
  'willow_verify_handoff',
]);

// The app_id argument every willow-mcp tool call requires. In serve mode
// (which is the only mode a browser tab can reach — see src/willow.js) the
// server ignores this and resolves the real identity from the signed-in
// session's operator-confirmed binding instead, so this is a placeholder to
// satisfy the schema, not a claim about who the call runs as.
const WILLOW_CALL_APP_ID = 'jarvis';

/** Normalizes a WillowSession#callTool result into the {data, text, isError} shape the UI expects. */
function fromWillowResult(result) {
  if (result.isError) return { data: result.data, text: result.text, isError: true };
  if (result.data && typeof result.data === 'object' && result.data.error) {
    return { data: result.data, text: `willow-mcp: ${result.data.error}`, isError: true };
  }
  return { data: result.data ?? result.text, text: result.data ? JSON.stringify(result.data, null, 2) : result.text };
}

async function readContext({ include_location = false } = {}) {
  const now = new Date();
  const ctx = {
    local_time: now.toLocaleString(),
    iso: now.toISOString(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    online: navigator.onLine,
  };

  if (navigator.getBattery) {
    try {
      const b = await navigator.getBattery();
      ctx.battery = { level: Math.round(b.level * 100), charging: b.charging };
    } catch (err) {
      ctx.battery = { unavailable: err.message };
    }
  } else {
    ctx.battery = { unavailable: 'Battery Status API not supported in this browser' };
  }

  if (include_location) {
    if (!navigator.geolocation) {
      ctx.location = { unavailable: 'Geolocation API not supported' };
    } else {
      ctx.location = await new Promise((resolve) => {
        const timer = setTimeout(() => resolve({ unavailable: 'timed out waiting for a fix' }), 8000);
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            clearTimeout(timer);
            resolve({
              // Deliberately coarse. Street-level precision is not needed for
              // anything this app does, and rounding here means it is never
              // written into memory or sent to the API in the first place.
              latitude: Number(pos.coords.latitude.toFixed(2)),
              longitude: Number(pos.coords.longitude.toFixed(2)),
              accuracy_note: 'rounded to ~1km',
            });
          },
          (err) => {
            clearTimeout(timer);
            resolve({ unavailable: err.message });
          },
          { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
        );
      });
    }
  }

  return ctx;
}

function resolveWhen({ in_minutes, at_iso }) {
  if (Number.isFinite(in_minutes)) return Date.now() + in_minutes * 60_000;
  if (at_iso) {
    const t = Date.parse(at_iso);
    if (Number.isFinite(t)) return t;
    throw new Error(`could not parse at_iso "${at_iso}"`);
  }
  throw new Error('set_reminder needs either in_minutes or at_iso');
}

/**
 * Build the dispatcher. Returns `run(name, input) -> { text, isError, data }`.
 * `text` is what the model sees; `data` is for the UI.
 *
 * Errors are returned as tool results with is_error rather than thrown, so a
 * bad tool call is something the model can read and recover from instead of
 * an exception that kills the turn.
 */
export function createToolRunner({
  memory,
  session,
  onReminderScheduled = () => {},
  // Whether a scheduled reminder survives the app being closed. Passed in
  // rather than assumed, because the honest sentence to say to the user is
  // the opposite depending on the answer, and the model can only get that
  // right if it is told which one is true right now.
  remindersDurable = false,
  // The WillowSession from src/willow.js, or null/undefined when the user
  // has never connected one. Optional because everything above this
  // parameter predates willow-mcp integration and must keep working with no
  // fleet connection at all.
  willow = null,
}) {
  const handlers = {
    async remember(input) {
      const fact = await memory.remember({ ...input, session });
      return {
        data: fact,
        text: `Stored fact ${fact.id} — subject "${fact.subject}", kind ${fact.kind}, provenance ${fact.provenance}.${
          fact.aliases.length
            ? ` Findable under: ${fact.aliases.join(', ')}.`
            : ' No aliases given, so this is only findable under words already in the subject or text.'
        }${fact.supersedes != null ? ` Fact ${fact.supersedes} is no longer live but is kept in history.` : ''}`,
      };
    },

    async recall(input = {}) {
      // Free text goes through the ranker; an explicit subject or kind is an
      // exact index lookup. Both are index-backed; they answer different
      // questions and the model picks by which it actually has.
      const { facts, provenance } = input.query
        ? await memory.search(input.query, { limit: input.limit || 20 })
        : await memory.recall(input);

      if (!facts.length) {
        return {
          data: { facts: [] },
          // "Nothing recorded" and "nothing is true" are different claims and
          // the model must not conflate them when answering.
          text:
            'No live facts matched. Note this means nothing has been recorded for that query — it is not evidence that the thing is untrue. ' +
            'Matching is lexical, so if you expected something, try recall again with different wording before concluding it is not there.',
        };
      }
      const lines = facts.map(
        (f) =>
          `#${f.id} [${f.kind}/${f.provenance}] ${f.subject}: ${f.text} (recorded ${new Date(f.createdAt).toLocaleDateString()}${
            f.matched ? `, matched: ${f.matched.join(', ')}` : ''
          })`,
      );
      return {
        data: { facts },
        text: `${facts.length} fact(s). Weakest provenance in this set: ${provenance} — any conclusion drawn from all of them is worth no more than that.\n${lines.join('\n')}`,
      };
    },

    async forget(input) {
      const row = await memory.forget(input.id);
      if (!row) return { data: null, text: `No fact with id ${input.id}.`, isError: true };
      return { data: row, text: `Fact ${row.id} retired. It no longer appears in recalls; the record is kept in history.` };
    },

    async set_reminder(input) {
      const at = resolveWhen(input);
      const row = await memory.addReminder({ at, text: input.text });
      await onReminderScheduled(row);
      return {
        data: row,
        text: `Reminder ${row.id} set for ${new Date(at).toLocaleString()}. ${
          remindersDurable
            ? 'It is scheduled with the operating system and will fire even if the app is closed.'
            : 'It fires only while this page is open; if the tab is closed it will be delivered when reopened.'
        }`,
      };
    },

    async list_reminders() {
      const rows = await memory.pendingReminders();
      if (!rows.length) return { data: { reminders: [] }, text: 'No pending reminders.' };
      return {
        data: { reminders: rows },
        text: rows.map((r) => `#${r.id} at ${new Date(r.at).toLocaleString()}: ${r.text}`).join('\n'),
      };
    },

    async get_context(input) {
      const ctx = await readContext(input || {});
      return { data: ctx, text: JSON.stringify(ctx, null, 2) };
    },

    async willow_whoami() {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('whoami', { app_id: WILLOW_CALL_APP_ID });
      return fromWillowResult(result);
    },

    async willow_dispatch_list(input = {}) {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('dispatch_list', { app_id: WILLOW_CALL_APP_ID, ...input });
      return fromWillowResult(result);
    },

    async willow_dispatch_read(input) {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('dispatch_read', { app_id: WILLOW_CALL_APP_ID, ...input });
      return fromWillowResult(result);
    },

    async willow_verify_handoff(input) {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('verify_handoff', { app_id: WILLOW_CALL_APP_ID, ...input });
      return fromWillowResult(result);
    },

    async willow_dispatch_send(input) {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('dispatch_send', { app_id: WILLOW_CALL_APP_ID, ...input });
      return fromWillowResult(result);
    },

    async willow_agent_clear(input) {
      if (!willow?.connected) {
        return { data: null, text: 'Not connected to willow-mcp. Tell the user to open settings and sign in.' };
      }
      const result = await willow.callTool('agent_clear', { app_id: WILLOW_CALL_APP_ID, ...input });
      return fromWillowResult(result);
    },
  };

  return async function run(name, input) {
    const handler = handlers[name];
    if (!handler) return { text: `Unknown tool "${name}".`, isError: true, data: null };
    try {
      const out = await handler(input || {});
      return { isError: false, ...out };
    } catch (err) {
      return { text: `Tool "${name}" failed: ${err.message}`, isError: true, data: null };
    }
  };
}
