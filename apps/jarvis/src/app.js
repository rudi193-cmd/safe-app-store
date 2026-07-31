// Wiring: capabilities -> memory -> model -> UI.

import { Memory } from './memory.js';
import { probeAll } from './capability.js';
import { Listener, Speaker, sentences } from './voice.js';
import { TOOL_DEFS, QUIET_TOOLS, createToolRunner } from './tools.js';
import { Assistant, buildMemoryContext } from './claude.js';
import { createPlatform } from './platform.js';

const $ = (id) => document.getElementById(id);
const KEY_STORE = 'jarvis.apiKey';
const EFFORT_STORE = 'jarvis.effort';
const SPEAK_STORE = 'jarvis.speak';

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
};

const caps = probeAll();
const memory = new Memory();
// Resolved at boot. Every rung is decided once and then reported, so the app
// never has to guess whether it is running in a tab or a native shell.
let platform = null;
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
  who.textContent = role === 'user' ? 'you' : role === 'assistant' ? 'jarvis' : role;
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
      new Notification('Jarvis', { body: r.text });
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
      tools: TOOL_DEFS,
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
  renderCapabilities();
  els.settings.showModal();
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
  window.__jarvis = { memory, caps, ask, history, createToolRunner, session, buildMemoryContext, platform };
  document.body.dataset.ready = '1';
}

boot().catch((err) => {
  addTurn('error', `Failed to start: ${err.message}`);
});
