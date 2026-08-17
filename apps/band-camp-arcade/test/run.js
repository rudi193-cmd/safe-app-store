// Test driver: serve band-camp-arcade over http, run all six game suites in
// real Chromium.
//
// http rather than file:// so this matches how the app is actually served
// (and so a future game that adds an ES module would work the same way the
// other non-Python app in this store, jarvis, already established the
// pattern for). The server can rewrite a source file on the way out, which is
// what makes mutation mode possible without touching the working tree.
//
//   node test/run.js              — run all six suites
//   node test/run.js --mutations  — verify each of the six gates can fail

import http from 'node:http';
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { MUTATIONS } from './mutations.js';
import { run as runTuning } from './suites/tuning.js';
import { run as runPitCrew } from './suites/pit-crew.js';
import { run as runSweatTracker } from './suites/sweat-tracker.js';
import { run as runBingo } from './suites/bingo.js';
import { run as runGeScoreRoast } from './suites/ge-score-roast.js';
import { run as runDrumMajor } from './suites/drum-major.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const GAMES = [
  { key: 'tuning-note-purgatory', label: 'Tuning Note Purgatory', run: runTuning },
  { key: 'pit-crew-simulator', label: 'Pit Crew Simulator', run: runPitCrew },
  { key: 'uniform-sweat-tracker', label: 'Uniform Sweat Tracker', run: runSweatTracker },
  { key: 'sectional-bingo', label: 'Sectional Bingo', run: runBingo },
  { key: 'ge-score-roast', label: 'GE Score Roast', run: runGeScoreRoast },
  { key: 'drum-major-says', label: 'Drum Major Says', run: runDrumMajor },
];

/**
 * Find an already-installed Chromium, same reasoning as jarvis/test/run.js:
 * the npm `playwright` package pins a browser build a pre-provisioned image
 * will not necessarily have, and downloading one is slow and often blocked.
 */
function resolveChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!base || !fsSync.existsSync(base)) return undefined;
  const candidates = fsSync
    .readdirSync(base)
    .filter((d) => d.startsWith('chromium-'))
    .sort()
    .reverse()
    .map((d) => path.join(base, d, 'chrome-linux', 'chrome'));
  return candidates.find((p) => fsSync.existsSync(p));
}

const EXECUTABLE = resolveChromium();

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

/** @param {{file: string, find: string, replace: string}|null} mutation */
function createServer(mutation) {
  return http.createServer(async (req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
    const abs = path.join(ROOT, rel);
    if (!abs.startsWith(ROOT)) {
      res.writeHead(403).end('no');
      return;
    }
    try {
      let body = await fs.readFile(abs, 'utf8');
      if (mutation && rel === mutation.file) body = body.replace(mutation.find, mutation.replace);
      res.writeHead(200, { 'content-type': TYPES[path.extname(abs)] || 'application/octet-stream' }).end(body);
    } catch {
      res.writeHead(404).end('not found');
    }
  });
}

async function withServer(mutation, fn) {
  const server = createServer(mutation);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
  try {
    return await fn(browser, `http://127.0.0.1:${port}`);
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

function summarise(results) {
  return {
    failed: results.filter((r) => !r.pass).map((r) => r.name),
    passed: results.filter((r) => r.pass).length,
    total: results.length,
  };
}

async function runAllSuites(mutation = null) {
  return withServer(mutation, async (browser, baseUrl) => {
    const all = [];
    for (const game of GAMES) {
      // eslint-disable-next-line no-await-in-loop
      const results = await game.run(browser, baseUrl);
      all.push(...results);
    }
    return all;
  });
}

async function main() {
  const wantMutations = process.argv.includes('--mutations');

  console.log('\n▸ suites (real Chromium, six games)\n');
  const baseline = await runAllSuites(null);
  for (const r of baseline) {
    console.log(`  ${r.pass ? '✓' : '✗'} ${r.name}`);
    if (!r.pass) console.log(`      ${String(r.error).split('\n').join('\n      ')}`);
  }
  const base = summarise(baseline);
  console.log(`\n  ${base.passed}/${base.total} passed`);

  if (base.failed.length) {
    console.error('\nsuites failed\n');
    process.exit(1);
  }

  if (!wantMutations) {
    console.log('\n(run with --mutations to verify these gates can actually fail)\n');
    return;
  }

  console.log('\n▸ mutations — each must redden exactly the gate(s) it declares\n');
  let bad = 0;
  for (const mutation of MUTATIONS) {
    // eslint-disable-next-line no-await-in-loop
    const source = await fs.readFile(path.join(ROOT, mutation.file), 'utf8');
    if (!source.includes(mutation.find)) {
      bad += 1;
      console.log(`  ✗ ${mutation.name} — ${mutation.describe}`);
      console.log(`      NOT APPLICABLE — the source moved; this gate no longer guards anything`);
      continue;
    }

    // eslint-disable-next-line no-await-in-loop
    const results = await runAllSuites(mutation);
    const { failed } = summarise(results);

    const expected = Array.isArray(mutation.expect) ? mutation.expect : [mutation.expect];
    const missed = expected.filter((n) => !failed.includes(n));
    const collateral = failed.filter((n) => !expected.includes(n));

    let verdict;
    if (missed.length) verdict = `NOT CAUGHT — still passed with the mechanism broken: ${missed.join(', ')}`;
    else if (collateral.length) verdict = `CAUGHT, but also reddened undeclared gates: ${collateral.join(', ')}`;
    else verdict = `caught, cleanly (${expected.length} gate${expected.length > 1 ? 's' : ''})`;

    const good = !missed.length && !collateral.length;
    if (!good) bad += 1;
    console.log(`  ${good ? '✓' : '✗'} ${mutation.name} — ${mutation.describe}`);
    console.log(`      ${verdict}`);
  }

  console.log(`\n  ${MUTATIONS.length - bad}/${MUTATIONS.length} gates verified\n`);
  if (bad) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
