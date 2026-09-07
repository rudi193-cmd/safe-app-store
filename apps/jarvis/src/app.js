// Wiring: capabilities -> memory -> model -> UI.

import { Memory } from './memory.js';
import { probeAll } from './capability.js';
import { Listener, Speaker, sentences } from './voice.js';
import { TOOL_DEFS, QUIET_TOOLS, createToolRunner, toModelTools } from './tools.js';
import { Assistant, buildMemoryContext } from './claude.js';
import { createPlatform } from './platform.js';
import { WillowSession, handleOAuthRedirect } from './willow.js';
import {
  ORGANS,
  WILLOW_MCP_SERVE_LOCAL,
  disclose,
  isLive,
  loadState,
  saveState,
  serveUrlLooksForbidden,
  setEnabled,
  toolDefsFor,
} from './composition.js';
import { depositJson } from './homecoming.js';

// A sign-in popup reloads this same page with `?code=...` in the query
// string. Its only job is to hand that back to the window that opened it and
// close — running the rest of boot() in the popup would stand up a second
// Memory/IndexedDB connection and UI for a window that is about to
// disappear.
if (handleOAuthRedirect()) {
  // The popup already handed its result to window.opener and called
  // window.close() inside handleOAuthRedirect(). Throwing here stops the
  // rest of this module — mic binding, a second Memory connection, boot() —
  // from running in a window that is already on its way out.
  throw new Error('willow-mcp sign-in popup: handed off to opener, closing');
}

const $ = (id) => document.getElementById(id);
const KEY_STORE = 'willow.apiKey';
const KEY_STORE_LEGACY = 'jarvis.apiKey';
const EFFORT_STORE = 'willow.effort';
const EFFORT_STORE_LEGACY = 'jarvis.effort';
const SPEAK_STORE = 'willow.speak';
const SPEAK_STORE_LEGACY = 'jarvis.speak';

const els = {
  transcript: $('transcript'),
  status: $('status'),
  mic: $('mic'),
  textForm: $('text-form'),
  textInput: $('text-input'),
  settings: $('settings'),
  settingsToggle: $('settings-toggle'),
  apiKey: $('api-key'),
  effort: $('effort'),
  speakToggle: $('speak-toggle'),
  capabilities: $('capabilities'),
  memory: $('memory'),
  memoryToggle: $('memory-toggle'),
  memoryList: $('memory-list'),
  memoryProvenance: $('memory-provenance'),
  wipe: $('wipe'),
  willowBaseUrl: $('willow-base-url'),
  willowStatus: $('willow-status'),
  willowConnect: $('willow-connect'),
  willowDisconnect: $('willow-disconnect'),
  compositionList: $('composition-list'),
  homecomingCopy: $('homecoming-copy'),
  homecomingStatus: $('homecoming-status'),
};

const caps = probeAll();
const memory = new Memory();
// Resolved at boot. Every rung is decided once and then reported, so the app
// never has to guess whether it is running in a tab or a native shell.
let platform = null;
// Resolved at boot, once platform.keys exists — see boot(). null until then,
// same pattern as platform itself.
let willow = null;
let compositionState = loadState();
let presentTools = [];
const speaker = new Speaker();
const session = `s-${Date.now().toString(36)}`;

/** The exact message list the API has seen, tool blocks included. */
const history = [];
let assistant = null;
let busy = false;

// --- rendering ---------------------------------------------------------------

function scroll() {
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function addTurn(role, text = '') {
  const el = document.createElement('div');
  el.className = `turn ${role}`;
  const who = document.createElement('div');
  who.className = 'who';
  who.textContent = role === 'user' ? 'you' : role === 'assistant' ? 'willow' : role;
  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = text;
  if (role !== 'notice' && role !== 'error') el.append(who);
  el.append(body);
  els.transcript.append(el);
  scroll();
  return body;
}

function addToolRow(name) {
  const row = document.createElement('div');
  row.className = 'tool';
  const label = document.createElement('span');
  label.className = 'name';
  label.textContent = name;
  const outcome = document.createElement('span');
  outcome.className = 'outcome';
  outcome.textContent = '…';
  row.append(label, outcome);
  els.transcript.append(row);
  scroll();
  return { row, outcome };
}

function setStatus(text, cls = '') {
  els.status.textContent = text;
  els.status.className = `status ${cls}`;
}

function renderCapabilities() {
  els.capabilities.replaceChildren();
  for (const cap of Object.values(caps)) {
    const li = document.createElement('li');
    const ok = cap.available;
    const head = document.createElement('span');
    head.className = ok ? 'yes' : 'no';
    head.textContent = `${ok ? '✓' : '—'} ${cap.name}${ok && cap.rung ? ` (${cap.rung})` : ''}`;
    li.append(head);
    // The notes are the point: a skipped rung says why it was skipped, so a
    // degraded session is legible instead of just quieter.
    for (const note of cap.notes) {
      const why = document.createElement('span');
      why.className = 'why';
      why.textContent = note;
      li.append(why);
    }
    els.capabilities.append(li);
  }
}

function renderWillowStatus() {
  els.willowStatus.textContent = willow?.connected
    ? `Signed in to ${willow.baseUrl}. This only proves a token was stored, not that it still works — ask "who are you connected as" to check.`
    : 'Not connected.';
}

function compositionApi() {
  return {
    isLive: (organId) => isLive(compositionState, organId, presentTools),
  };
}

function liveToolDefs() {
  return toolDefsFor(TOOL_DEFS, compositionState, presentTools);
}

function renderComposition() {
  if (!els.compositionList) return;
  els.compositionList.replaceChildren();
  for (const organ of ORGANS) {
    const li = document.createElement('li');
    const live = isLive(compositionState, organ.id, presentTools);
    const present = (presentTools || []).some((name) => organ.detectTools.includes(name));
    const head = document.createElement('span');
    head.className = live ? 'yes' : 'no';
    head.textContent = `${live ? '✓' : '—'} ${organ.name}${present ? ' (server lists it)' : ' (absent on server)'}`;
    li.append(head);

    const possible = document.createElement('span');
    possible.className = 'why';
    possible.textContent = `possible: ${organ.possible.join('; ')}`;
    const reachable = document.createElement('span');
    reachable.className = 'why';
    reachable.textContent = `reachable: ${organ.reachable.join('; ')}`;
    li.append(possible, reachable);

    const discloseBtn = document.createElement('button');
    discloseBtn.type = 'button';
    discloseBtn.className = 'ghost';
    discloseBtn.textContent = compositionState.disclosed[organ.id] ? 'Disclosed' : 'Disclose';
    discloseBtn.disabled = Boolean(compositionState.disclosed[organ.id]);
    discloseBtn.addEventListener('click', () => {
      compositionState = saveState(disclose(compositionState, organ.id));
      renderComposition();
    });

    const enableBtn = document.createElement('button');
    enableBtn.type = 'button';
    enableBtn.className = 'ghost';
    const on = Boolean(compositionState.enabled[organ.id]);
    enableBtn.textContent = on ? 'Disable' : 'Enable';
    enableBtn.addEventListener('click', () => {
      try {
        compositionState = saveState(setEnabled(compositionState, organ.id, !on));
      } catch (err) {
        addTurn('notice', err.message);
      }
      renderComposition();
    });
    li.append(discloseBtn, enableBtn);
    els.compositionList.append(li);
  }
}

async function refreshPresentTools() {
  presentTools = [];
  if (!willow?.connected) return;
  try {
    presentTools = await willow.listTools();
  } catch (err) {
    presentTools = [];
    els.willowStatus.textContent = `Signed in, but tools/list failed: ${err.message}`;
  }
}

async function renderMemory() {
  const { facts, provenance } = await memory.recall({ limit: 200 });
  els.memoryProvenance.textContent = facts.length
    ? `${facts.length} live fact(s). Weakest provenance here: ${provenance}. Superseded facts are kept but not shown.`
    : 'Nothing recorded yet.';
  els.memoryList.replaceChildren();
  for (const f of facts) {
    const li = document.createElement('li');
    const tag = document.createElement('span');
    tag.className = `tag ${f.provenance}`;
    tag.textContent = `${f.kind}·${f.provenance}`;
    const text = document.createElement('span');
    text.textContent = `${f.subject} — ${f.text}`;
    li.append(tag, text);
    // Show the aliases: they are the difference between a fact you can find
    // again and one that is only reachable if you happen to use the same word
    // twice. Worth being able to see when something turns out to be missing.
    if (f.aliases?.length) {
      const also = document.createElement('span');
      also.className = 'also';
      also.textContent = `also: ${f.aliases.join(', ')}`;
      li.append(also);
    }
    els.memoryList.append(li);
  }
}

// --- reminders ---------------------------------------------------------------

async function fireDueReminders() {
  const due = await memory.dueReminders();
  for (const r of due) {
    await memory.markFired(r.id);
    addTurn('notice', `Reminder: ${r.text}`);
    speaker.say(`Reminder. ${r.text}`);
    // Only announce it ourselves when the OS is not already doing it. On the
    // durable rung the notification has been scheduled with the system since
    // the moment it was set, so posting one here would fire it twice.
    if (!platform?.reminders.durable && typeof Notification === 'function' && Notification.permission === 'granted') {
      new Notification('Willow', { body: r.text });
    }
  }
}

// --- the turn ----------------------------------------------------------------

let cachedKey = null;

function ensureAssistant() {
  const key = cachedKey;
  if (!key) return null;
  const effort = localStorage.getItem(EFFORT_STORE) || 'low';
  if (!assistant || assistant.effort !== effort || assistant.key !== key) {
    assistant = new Assistant({ apiKey: key, effort });
    assistant.key = key;
  }
  return assistant;
}

async function ask(userText) {
  const text = String(userText || '').trim();
  if (!text || busy) return;

  const model = ensureAssistant();
  if (!model) {
    addTurn('error', 'No API key set. Open settings and paste one.');
    els.settings.showModal();
    return;
  }

  busy = true;
  els.textInput.value = '';
  addTurn('user', text);
  setStatus('thinking…');

  const body = addTurn('assistant');
  body.classList.add('pending');

  // Sentence buffer: speak complete sentences as they stream rather than
  // token soup, and without waiting for the whole reply.
  let spokenTail = '';
  const runTool = createToolRunner({
    memory,
    session,
    willow,
    composition: compositionApi(),
    remindersDurable: Boolean(platform?.reminders.durable),
    onReminderScheduled: async (row) => {
      // Hand it to the OS when we can. `schedule` returns false on the web
      // rung, which is the signal that the in-page timer is still the only
      // thing that will deliver this.
      const handedOff = await platform?.reminders.schedule(row);
      if (!handedOff) scheduleTick();
    },
  });

  try {
    const memoryContext = await buildMemoryContext(memory, text);

    await model.send({
      history,
      userText: text,
      memoryContext,
      tools: toModelTools(liveToolDefs()),
      runTool,
      onText: (delta) => {
        body.textContent += delta;
        spokenTail += delta;
        const { spoken, rest } = sentences(spokenTail);
        spokenTail = rest;
        for (const s of spoken) speaker.say(s);
        scroll();
      },
      onToolStart: (call) => {
        const handle = addToolRow(call.name);
        call.__ui = handle;
        setStatus(`running ${call.name}…`);
      },
      onToolEnd: (call, result) => {
        const handle = call.__ui;
        if (!handle) return;
        if (result.isError) handle.row.classList.add('err');
        handle.outcome.textContent = result.text.split('\n')[0].slice(0, 90);
        if (!QUIET_TOOLS.has(call.name)) renderMemory();
      },
      onNotice: (msg) => addTurn('notice', msg),
    });

    if (spokenTail.trim()) speaker.say(spokenTail);
  } catch (err) {
    addTurn('error', `${err.name || 'Error'}: ${err.message}`);
  } finally {
    body.classList.remove('pending');
    // An assistant turn that produced only tool calls leaves an empty bubble.
    if (!body.textContent.trim()) body.parentElement.remove();
    busy = false;
    setStatus('');
    renderMemory();
  }
}

// --- reminder ticking --------------------------------------------------------

let tick = null;
function scheduleTick() {
  if (tick) clearInterval(tick);
  tick = setInterval(fireDueReminders, 15_000);
}

// --- input -------------------------------------------------------------------

const listener = new Listener({
  onPartial: (t) => setStatus(t || 'listening…', 'listening'),
  onFinal: (t) => {
    setStatus('');
    ask(t);
  },
  onError: (e) => setStatus(`mic: ${e}`),
});

function bindMic() {
  if (!listener.available) {
    els.mic.disabled = true;
    els.mic.title = listener.capability.notes.join('; ');
    return;
  }
  const start = (event) => {
    event.preventDefault();
    if (busy) return;
    // Barge-in: talking over the assistant should stop it talking.
    speaker.stop();
    platform?.haptics.tap();
    els.mic.classList.add('on');
    setStatus('listening…', 'listening');
    listener.start();
  };
  const stop = () => {
    els.mic.classList.remove('on');
    listener.stop();
  };
  els.mic.addEventListener('pointerdown', start);
  els.mic.addEventListener('pointerup', stop);
  els.mic.addEventListener('pointercancel', stop);
  els.mic.addEventListener('pointerleave', stop);
}

els.textForm.addEventListener('submit', (e) => {
  e.preventDefault();
  ask(els.textInput.value);
});

// --- settings ----------------------------------------------------------------

els.settingsToggle.addEventListener('click', () => {
  els.apiKey.value = cachedKey || '';
  els.effort.value = localStorage.getItem(EFFORT_STORE) || 'low';
  els.speakToggle.checked = localStorage.getItem(SPEAK_STORE) !== 'off';
  els.willowBaseUrl.value = willow?.baseUrl || WILLOW_MCP_SERVE_LOCAL;
  renderWillowStatus();
  renderComposition();
  renderCapabilities();
  els.settings.showModal();
});

els.willowConnect.addEventListener('click', async () => {
  if (!willow) {
    els.willowStatus.textContent = 'Still starting up — try again in a moment.';
    return;
  }
  const baseUrl = els.willowBaseUrl.value.trim();
  if (!baseUrl) {
    els.willowStatus.textContent = 'Enter a willow-mcp serve URL first.';
    return;
  }
  if (serveUrlLooksForbidden(baseUrl)) {
    els.willowStatus.textContent = 'Refused: :8766 is the Grove desk (D4 loopback). Sign in to willow-mcp --serve (local :8768).';
    return;
  }
  els.willowStatus.textContent = 'Opening sign-in…';
  try {
    await willow.signIn(baseUrl);
    await refreshPresentTools();
    renderWillowStatus();
    renderComposition();
  } catch (err) {
    els.willowStatus.textContent = `Sign-in failed: ${err.message}`;
  }
});

els.willowDisconnect.addEventListener('click', async () => {
  if (!willow) return;
  await willow.signOut();
  presentTools = [];
  renderWillowStatus();
  renderComposition();
});

els.homecomingCopy?.addEventListener('click', async () => {
  const { facts } = await memory.recall({ limit: 2000 });
  const text = depositJson(facts);
  try {
    await navigator.clipboard.writeText(text);
    els.homecomingStatus.textContent = `Copied ${facts.length} fact(s) as a phone-seat-deposit.`;
  } catch {
    els.homecomingStatus.textContent = 'Clipboard refused — deposit is in the last notice.';
    addTurn('notice', text);
  }
});

els.settings.addEventListener('close', async () => {
  const key = els.apiKey.value.trim();
  cachedKey = key || null;
  if (key) await platform.keys.set(KEY_STORE, key);
  else await platform.keys.remove(KEY_STORE);
  localStorage.setItem(EFFORT_STORE, els.effort.value);
  localStorage.setItem(SPEAK_STORE, els.speakToggle.checked ? 'on' : 'off');
  speaker.enabled = els.speakToggle.checked;
  if (!speaker.enabled) speaker.stop();
  assistant = null;
  // Asking for notification permission on a real interaction, not on load.
  if (typeof Notification === 'function' && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {});
  }
});

els.memoryToggle.addEventListener('click', async () => {
  await renderMemory();
  els.memory.showModal();
});

els.wipe.addEventListener('click', async () => {
  if (!confirm('Delete every stored fact and reminder? This cannot be undone.')) return;
  await memory.wipe();
  await renderMemory();
  addTurn('notice', 'Memory cleared.');
});

// --- boot --------------------------------------------------------------------

async function boot() {
  await memory.open();
  // Before the capability panel or the key read, so both see resolved rungs.
  platform = await createPlatform();
  caps.reminderDurability = {
    name: 'reminder-durability',
    available: platform.reminders.durable,
    rung: platform.reminders.rung,
    durable: platform.reminders.durable,
    notes: platform.reminders.notes,
  };
  caps.keyStorage = {
    name: 'key-storage',
    available: platform.keys.appPrivate,
    rung: platform.keys.rung,
    notes: platform.keys.notes,
  };
  cachedKey = await platform.keys.get(KEY_STORE);
  if (!cachedKey) {
    const legacy = await platform.keys.get(KEY_STORE_LEGACY);
    if (legacy) {
      cachedKey = legacy;
      await platform.keys.set(KEY_STORE, legacy);
    }
  }
  if (!localStorage.getItem(EFFORT_STORE) && localStorage.getItem(EFFORT_STORE_LEGACY)) {
    localStorage.setItem(EFFORT_STORE, localStorage.getItem(EFFORT_STORE_LEGACY));
  }
  if (!localStorage.getItem(SPEAK_STORE) && localStorage.getItem(SPEAK_STORE_LEGACY)) {
    localStorage.setItem(SPEAK_STORE, localStorage.getItem(SPEAK_STORE_LEGACY));
  }
  // Loads any config + tokens saved from a previous sign-in. A missing or
  // expired token surfaces the first time a willow_ tool is actually called,
  // not here — this just restores what was stored.
  willow = await new WillowSession({ keys: platform.keys }).load();
  try {
    if (await willow.completeSignInFromRedirect()) {
      addTurn('notice', 'Signed in to willow-mcp.');
    }
  } catch (err) {
    addTurn('error', `Sign-in failed: ${err.message}`);
  }
  await refreshPresentTools();
  speaker.enabled = localStorage.getItem(SPEAK_STORE) !== 'off';
  bindMic();
  renderCapabilities();
  await renderMemory();
  scheduleTick();
  await fireDueReminders();

  if (!cachedKey) {
    addTurn('notice', 'Add an Anthropic API key in settings to start. Hold the circle to talk, or type.');
  } else {
    setStatus('ready');
  }

  // Test seam. The Playwright suite in test/ drives the real modules in real
  // Chromium through this handle — the browser APIs underneath (IndexedDB
  // transactions, index cursors) have no Node equivalent, so a Node-only
  // suite would be asserting against a stand-in that never runs in
  // production. See test/README notes in jarvis/README.md.
  window.__jarvis = { memory, caps, ask, history, createToolRunner, session, buildMemoryContext, platform, willow };
  window.__willow = window.__jarvis;
  document.body.dataset.ready = '1';
}

boot().catch((err) => {
  addTurn('error', `Failed to start: ${err.message}`);
});
