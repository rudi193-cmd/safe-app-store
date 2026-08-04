/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Offline after first load, and the mechanism behind `network: none`.
 *
 * P4's gate is "works fully offline after first load, on a Chromebook, from a
 * static host" — and explicitly not from file://, where a null origin kills
 * fetch, WASM, modules and OPFS alike.
 *
 * This worker precaches the shell and then serves only from the cache. A request
 * that misses is not fetched: it fails. That is stronger than cache-first and it
 * is what makes the privacy claim a mechanism rather than a promise — there is
 * no code path here that reaches the network, so there is nothing to audit for
 * one. The page's CSP says connect-src 'none' for the same reason, and
 * test/network.test.mjs fails if either statement drifts from the other.
 */

const VERSION = 'shell-1';

const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './styles/tokens.css',
  './styles/shell.css',
  './src/shell.js',
  './src/capabilities.js',
  './src/storage.js',
  './assets/icon.svg',
  './assets/icon-192.png',
  './assets/icon-512.png',
  './assets/icon-512-maskable.png',
  './assets/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  // Same-origin only, and cache-only. No fetch() appears anywhere in this file.
  if (new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then((hit) =>
      hit ?? caches.match('./index.html').then((shell) =>
        shell ?? new Response('offline, and this was never cached', { status: 504 }),
      ),
    ),
  );
});
