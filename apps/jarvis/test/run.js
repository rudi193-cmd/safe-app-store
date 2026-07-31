// Test driver: serve jarvis/ over http, run the suite in real Chromium.
//
// http rather than file:// because ES modules are blocked under file://, and
// real Chromium rather than a Node IndexedDB shim because the shim is the
// thing that would need testing. The server can rewrite a source file on the
// way out, which is what makes the mutation mode possible without touching
// the working tree.
//
//   node test/run.js              — run the suite
//   node test/run.js --mutations  — verify each gate can actually fail

import http from 'node:http';
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { MUTATIONS } from './mutations.js';
import { checkPluginApi, checkPackaging } from './plugin-api.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/**
 * Find an already-installed Chromium.
 *
 * The npm `playwright` package pins a browser build that a pre-provisioned
 * image will not necessarily have, and downloading one is both slow and often
 * blocked. Prefer whatever is on disk; fall back to Playwright's own default
 * only when nothing is found, so a normal `npx playwright install` machine
 * still works untouched.
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

async function runSuite(mutation = null) {
  const server = createServer(mutation);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();

  const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('pageerror', (err) => consoleErrors.push(err.message));

  let results;
  try {
    await page.goto(`http://127.0.0.1:${port}/test/index.html`, { waitUntil: 'load' });
    await page.waitForSelector('body[data-done="1"]', { timeout: 45_000 });
    results = await page.evaluate(() => window.__results);
  } catch (err) {
    results = [{ name: '<suite did not complete>', pass: false, error: `${err.message}` }];
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (consoleErrors.length) {
    results.push({ name: '<no uncaught page errors>', pass: false, error: consoleErrors.join('\n') });
  }
  return results;
}

/**
 * Boot the real app page.
 *
 * The suite imports individual modules; it never loads index.html, app.js, or
 * the vendored SDK bundle. Without this, every module could be correct and
 * the page could still be white — a broken import path, a stubbed node
 * builtin the SDK actually reaches at construction time, a typo in the
 * markup. This is the gate for "the thing starts".
 */
async function runBoot() {
  const server = createServer(null);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();

  const browser = await chromium.launch(EXECUTABLE ? { executablePath: EXECUTABLE } : {});
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(err.message));
  page.on('requestfailed', (r) => errors.push(`request failed: ${r.url()}`));

  const results = [];
  try {
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'load' });
    await page.waitForSelector('body[data-ready="1"]', { timeout: 20_000 });
    results.push({ name: 'app boots and opens its database', pass: true });

    // Constructing the client is where the SDK would reach for a node builtin
    // if the browser bundle were wrong, so build one for real. A bogus key is
    // fine — nothing is sent.
    const clientOk = await page.evaluate(async () => {
      const { Assistant } = await import('/src/claude.js');
      const a = new Assistant({ apiKey: 'sk-ant-not-a-real-key', effort: 'low' });
      return typeof a.send === 'function';
    });
    results.push({
      name: 'vendored SDK constructs a browser client',
      pass: clientOk,
      error: clientOk ? undefined : 'Assistant did not construct',
    });

    const caps = await page.evaluate(() => Object.keys(window.__jarvis.caps));
    results.push({
      name: 'capabilities are probed at boot',
      pass: caps.length >= 5,
      error: caps.length >= 5 ? undefined : `only probed: ${caps.join(', ')}`,
    });
  } catch (err) {
    results.push({ name: 'app boots and opens its database', pass: false, error: err.message });
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (errors.length) {
    results.push({ name: 'app boots with no uncaught errors', pass: false, error: errors.join('\n') });
  } else {
    results.push({ name: 'app boots with no uncaught errors', pass: true });
  }
  return results;
}

function summarise(results) {
  return {
    failed: results.filter((r) => !r.pass).map((r) => r.name),
    passed: results.filter((r) => r.pass).length,
    total: results.length,
  };
}

/**
 * Build `www/` before the packaging checks read it.
 *
 * Found on the re-land into safe-app-store, and it is the shape marching-arts'
 * browser port warns about in its own `.gitignore`: `www/` is generated and not
 * committed, so a fresh checkout has none. The packaging checks read whatever
 * is on disk, so locally — where a `www/` from an earlier build is lying around
 * — they passed, and on a clean clone five of them failed.
 *
 * Building on every run rather than only when missing is the same reasoning
 * that port applies to its differential reference: a stale artifact agrees with
 * the checks forever, and that is indistinguishable from a real pass. The build
 * is a file copy and costs milliseconds.
 */
async function buildWww() {
  const { execFile } = await import('node:child_process');
  const { promisify } = await import('node:util');
  await promisify(execFile)(process.execPath, [path.join(ROOT, 'scripts', 'build-www.js')], {
    cwd: ROOT,
  });
}

async function main() {
  const wantMutations = process.argv.includes('--mutations');

  console.log('\n▸ capacitor conformance & packaging (static — no APK can be built here)\n');
  await buildWww();
  const api = [...(await checkPluginApi(ROOT)), ...(await checkPackaging(ROOT))];
  const apiFailed = api.filter((r) => !r.pass);
  for (const r of apiFailed) console.log(`  ✗ ${r.name}\n      ${r.error}`);
  console.log(`  ${api.length - apiFailed.length}/${api.length} checks passed (plugin symbols against installed definitions, plus packaging)`);
  if (apiFailed.length) {
    console.error('\ncapacitor conformance failed\n');
    process.exit(1);
  }

  console.log('\n▸ boot (the real page, the real SDK bundle)\n');
  const boot = await runBoot();
  for (const r of boot) {
    console.log(`  ${r.pass ? '✓' : '✗'} ${r.name}`);
    if (!r.pass) console.log(`      ${String(r.error).split('\n').join('\n      ')}`);
  }
  if (boot.some((r) => !r.pass)) {
    console.error('\nboot failed\n');
    process.exit(1);
  }

  console.log('\n▸ suite (real Chromium, real IndexedDB)\n');
  const baseline = await runSuite(null);
  for (const r of baseline) {
    console.log(`  ${r.pass ? '✓' : '✗'} ${r.name}${r.ms != null ? ` (${r.ms}ms)` : ''}`);
    if (!r.pass) console.log(`      ${String(r.error).split('\n').join('\n      ')}`);
  }
  const base = summarise(baseline);
  console.log(`\n  ${base.passed}/${base.total} passed`);

  if (base.failed.length) {
    console.error('\nsuite failed\n');
    process.exit(1);
  }

  if (!wantMutations) {
    console.log('\n(run with --mutations to verify these gates can actually fail)\n');
    return;
  }

  console.log('\n▸ mutations — each must redden exactly the gates it declares\n');
  let bad = 0;
  for (const mutation of MUTATIONS) {
    // `expect` is a set, not a single name. A mechanism that four distinct
    // behaviours genuinely depend on *should* redden four gates; insisting on
    // exactly one would push you to write mutations so narrow they stop
    // corresponding to a real way the code could break. The check stays sharp
    // because it is exact in both directions: every declared gate must fail,
    // and no undeclared gate may.
    const expected = Array.isArray(mutation.expect) ? mutation.expect : [mutation.expect];

    // Applicability is checked here rather than at serve time. A mutation
    // whose `find` no longer matches used to be served as a 500, which broke
    // the module import, which failed every test at once — indistinguishable
    // from a mutation that simply was not caught. Checking up front separates
    // "this gate stopped guarding anything" from "this gate is blunt".
    // eslint-disable-next-line no-await-in-loop
    const source = await fs.readFile(path.join(ROOT, mutation.file), 'utf8');
    if (!source.includes(mutation.find)) {
      bad += 1;
      console.log(`  ✗ ${mutation.name} — ${mutation.describe}`);
      console.log(`      NOT APPLICABLE — the source moved; this gate no longer guards anything`);
      continue;
    }

    // eslint-disable-next-line no-await-in-loop
    const results = await runSuite(mutation);
    const { failed } = summarise(results);

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
