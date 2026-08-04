/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The shell: chrome, theme, nav, status. It mounts capabilities and has none.
 */

import { EMPTY_STATE, capabilities } from './capabilities.js';
import { describeStorage, probeStorage } from './storage.js';

const $ = (id) => document.getElementById(id);

function applyTheme(choice) {
  const root = document.documentElement;
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);
  for (const button of document.querySelectorAll('[data-theme-choice]')) {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === choice));
  }
  try {
    localStorage.setItem('theme', choice);
  } catch {
    // Private mode, or storage denied. The theme still applies for this session;
    // failing to persist a preference is not worth breaking the shell over.
  }
}

function renderCapabilities() {
  const list = $('nav-capabilities');
  const view = $('view');
  const registered = capabilities();
  list.replaceChildren();

  if (registered.length === 0) {
    const note = document.createElement('li');
    note.className = 'nav-empty';
    note.textContent = 'none yet';
    list.append(note);

    const title = document.createElement('h1');
    title.textContent = EMPTY_STATE.title;
    const body = document.createElement('p');
    body.className = 'measure';
    body.textContent = EMPTY_STATE.body;
    view.replaceChildren(title, body);
    view.setAttribute('aria-busy', 'false');
    return;
  }

  for (const capability of registered) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.className = 'nav-link';
    link.href = `#/${capability.id}`;
    link.textContent = capability.title;
    item.append(link);
    list.append(item);
  }
  view.replaceChildren();
  registered[0].mount(view);
  view.setAttribute('aria-busy', 'false');
}

function renderStorage() {
  const state = probeStorage();
  $('storage-status-text').textContent = describeStorage(state);
  // A non-durable session is a fact the user should be able to see, not a
  // detail buried in a console log.
  $('storage-status').classList.toggle('warn', !state.durable);
}

function main() {
  let stored = null;
  try {
    stored = localStorage.getItem('theme');
  } catch {
    stored = null;
  }
  applyTheme(stored ?? 'system');
  for (const button of document.querySelectorAll('[data-theme-choice]')) {
    button.addEventListener('click', () => applyTheme(button.dataset.themeChoice));
  }

  const toggle = $('nav-toggle');
  toggle.addEventListener('click', () => {
    const open = document.body.classList.toggle('nav-open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  renderCapabilities();
  renderStorage();

  // Registered from the page rather than bundled, so the shell still works with
  // the worker unavailable — which is what happens on the first load, and in
  // any browser where the user has disabled it.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {
      $('net-status-text').textContent = 'Offline support unavailable';
    });
  } else {
    $('net-status-text').textContent = 'Offline support unavailable';
  }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', main);
else main();
