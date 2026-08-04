/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The wiring, watched happening.
 *
 *   make demo app=marching-arts-shell        # from the repo root
 *   node demo.mjs                            # from here
 *
 * apps/marching-arts/app.py says it exists "so the guarantees can be watched
 * happening rather than read about, which is a different kind of convincing
 * than a passing test suite". Same reason. This chassis ships no capability, so
 * there is nothing to look at — what there is to look at is the wiring, and
 * every seam in it makes a claim that is either mechanised or a wish.
 *
 * It serves the shell over real HTTP on an ephemeral port, because P4's gate
 * says "from a static host" and explicitly not file://, where a null origin
 * kills fetch, WASM, modules and OPFS alike. Then it drives a real Chromium
 * through the claims, including the one no unit test here could reach: cut the
 * network and reload, and see whether the thing still comes up.
 *
 * Exits non-zero if a step does not do what it says. A demo that cannot fail is
 * a screenshot.
 */

import { createServer } from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright-core';

import { CANON, construct } from './mark/construct.mjs';
import { check } from './mark/invariants.mjs';
import { findChrome } from './mark/rasterise.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, 'web');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

let step = 0;
const say = (title) => process.stdout.write(`\n${String(++step).padStart(2)}. ${title}\n`);
const line = (text) => process.stdout.write(`    ${text}\n`);
const fail = (why) => {
  process.stdout.write(`\n    FAILED: ${why}\n`);
  process.exitCode = 1;
  throw new Error(why);
};
const ok = (condition, why) => (condition ? true : fail(why));

/** A static host, which is what the gate names. Serves web/ and nothing else. */
function serve() {
  const requests = [];
  const server = createServer((req, res) => {
    requests.push(req.url);
    const path = req.url === '/' ? '/index.html' : req.url.split('?')[0];
    const file = join(web, decodeURIComponent(path));
    if (!file.startsWith(web) || !existsSync(file)) {
      res.writeHead(404).end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' });
    res.end(readFileSync(file));
  });
  return new Promise((done) => {
    server.listen(0, '127.0.0.1', () => done({ server, requests, port: server.address().port }));
  });
}

const { server, requests, port } = await serve();
const origin = `http://127.0.0.1:${port}`;
let browser = null;

try {
  /* ---------------------------------------------------------------- the mark */

  say('The mark is derived, not drawn.');
  const geo = construct(CANON);
  const d = geo.derived;
  line(`spec      N ${d.N}, R ${d.R}, span ${d.span}, phase ${geo.spec.phase}`);
  line(`derived   side ${d.side.toFixed(4)} = 2R·sin(π·span/N), aperture ${d.aperture}°`);
  line(`          trim ${d.trim.toFixed(4)}°, sweep ${d.sweep.toFixed(4)}°, box ${d.box}`);
  line(`          emitted at ${d.precision} decimals — searched for, not chosen`);
  const verdicts = check(geo);
  const failed = verdicts.filter((v) => v.applies && !v.ok);
  line(`${verdicts.filter((v) => v.applies).length} invariants apply, ${failed.length} fail`);
  ok(failed.length === 0, `the shipped mark fails: ${failed.map((f) => f.name).join(', ')}`);

  say('The same construction refuses what it cannot draw honestly.');
  for (const spec of [{ N: 4, span: 2 }, { gapRatio: 20 }]) {
    try {
      construct({ ...CANON, ...spec });
      fail(`${JSON.stringify(spec)} was not refused`);
    } catch (error) {
      line(`${JSON.stringify(spec)} → ${error.message.split(':')[0]}`);
    }
  }

  say('And it names what a different spec would break.');
  for (const spec of [{ N: 4, span: 1 }, { N: 9, span: 4 }]) {
    const broke = check(construct({ ...CANON, ...spec })).filter((v) => v.applies && !v.ok);
    line(`${JSON.stringify(spec)} → ${broke.map((b) => b.name).join('; ') || 'nothing'}`);
    ok(broke.length > 0, `${JSON.stringify(spec)} tripped no gate`);
  }

  /* -------------------------------------------------------------- the shell */

  const chrome = findChrome();
  browser = await chromium.launch({ executablePath: chrome, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  const page = await context.newPage();

  const offOrigin = [];
  page.on('request', (r) => {
    if (!r.url().startsWith(origin) && !r.url().startsWith('data:')) offOrigin.push(r.url());
  });

  say(`Served from a static host — ${origin}, not file://.`);
  await page.goto(origin, { waitUntil: 'networkidle' });
  line(`title: ${await page.title()}`);
  ok((await page.locator('.wordmark-glyph').count()) === 1, 'the mark is not in the app bar');
  line(`the mark is in the app bar, ${await page.locator('.wordmark-glyph path').count()} arcs and ` +
    `${await page.locator('.wordmark-glyph circle').count()} sources`);

  say('The storage seam reports which rung it got. It does not assume.');
  const storage = await page.locator('#storage-status-text').textContent();
  line(`status bar says: "${storage.trim()}"`);
  const probe = await page.evaluate(async () => {
    const { probeStorage } = await import('./src/storage.js');
    return probeStorage();
  });
  line(`rung ${probe.name}, durable ${probe.durable}`);
  for (const note of probe.notes) line(`skipped — ${note}`);
  ok(typeof probe.durable === 'boolean', 'durability was not reported at all');

  say('The capability seam is empty, and says why rather than pretending.');
  line(`heading: "${(await page.locator('#view h1').textContent()).trim()}"`);
  const body = (await page.locator('#view p.measure').textContent()).trim();
  line(`body:    "${body.slice(0, 96)}…"`);
  ok(/open question/.test(body), 'the empty state stopped explaining itself');
  ok((await page.locator('#nav-capabilities li.nav-empty').count()) === 1, 'nav is not empty');

  say('The service worker registers and precaches the shell.');
  const cached = await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    const names = await caches.keys();
    const cache = await caches.open(names[0]);
    return { names, entries: (await cache.keys()).length };
  });
  line(`cache "${cached.names.join(', ')}" holds ${cached.entries} entries`);
  ok(cached.entries >= 10, `only ${cached.entries} entries precached`);

  say('Now cut the network and reload. This is the claim no unit test here reaches.');
  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  const offlineTitle = await page.title();
  const offlineHeading = (await page.locator('#view h1').textContent()).trim();
  line(`offline reload → "${offlineTitle}", view renders "${offlineHeading}"`);
  ok(offlineHeading.length > 0, 'the shell did not render with the network cut');
  ok((await page.locator('.wordmark-glyph').count()) === 1, 'the mark did not survive the reload');
  await context.setOffline(false);

  say('network: none — nothing was ever asked of anywhere else.');
  line(`${requests.length} requests to this host, ${offOrigin.length} to any other`);
  ok(offOrigin.length === 0, `reached off-origin: ${offOrigin.join(', ')}`);

  process.stdout.write('\n    Every step did what it said.\n');
  process.stdout.write('    Not shown, and not claimed: a Chromebook. P4\'s gate names one.\n\n');
} finally {
  await browser?.close();
  server.close();
}
