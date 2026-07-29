/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * A static server for the browser-mechanism gate, and nothing else.
 *
 * Two jobs, both forced on us by what OPFS needs:
 *
 *   1. **A secure context.** `file://` is a null origin and has no OPFS at all,
 *      so the pages under test have to come off a real origin. `http://127.0.0.1`
 *      counts as a secure context, so this needs no TLS.
 *   2. **Bare specifier resolution.** `dist/open.js` imports
 *      `@sqlite.org/sqlite-wasm`, which a browser cannot resolve. An import map
 *      would fix it for the *page* and not for the SharedWorker — import maps are
 *      document-scoped and workers do not get one. So the rewrite happens here,
 *      on the way out, for every module this serves. Nothing on disk is touched;
 *      `dist/` stays exactly what `tsc` produced, which matters because
 *      `mutate-browser.mjs` edits those same files and restores them by hash.
 *
 * Files are read per request with no caching, so a mutation applied between two
 * page loads is actually seen by the second one.
 */

import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const VENDOR = resolve(ROOT, 'node_modules', '@sqlite.org', 'sqlite-wasm', 'dist');

/** Where the browser will find the sqlite-wasm ES module. */
export const VENDOR_URL = '/vendor/sqlite-wasm/index.mjs';

const TYPES = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.map', 'application/json; charset=utf-8'],
  ['.wasm', 'application/wasm'],
  ['.css', 'text/css; charset=utf-8'],
]);

function extname(path) {
  const dot = path.lastIndexOf('.');
  return dot === -1 ? '' : path.slice(dot);
}

/**
 * Rewrite the one bare specifier this tree uses.
 *
 * Deliberately narrow: it matches the exact module string in an import or
 * export clause and nothing else. A general-purpose bundler here would be a
 * second build of the thing under test, and then a green run would be evidence
 * about the bundle rather than about `dist/`.
 */
export function rewriteSpecifiers(source) {
  return source.replace(
    /(from\s*|import\s*\(\s*)(['"])@sqlite\.org\/sqlite-wasm\2/g,
    (_all, lead, quote) => `${lead}${quote}${VENDOR_URL}${quote}`,
  );
}

function resolveRequest(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
  if (clean.startsWith('/vendor/sqlite-wasm/')) {
    const file = clean.slice('/vendor/sqlite-wasm/'.length);
    const full = resolve(VENDOR, file);
    return full.startsWith(VENDOR + sep) ? full : null;
  }
  const full = resolve(join(ROOT, clean));
  // Confine to the package, and never serve node_modules except through /vendor.
  if (!full.startsWith(ROOT + sep) && full !== ROOT) return null;
  if (full.startsWith(join(ROOT, 'node_modules') + sep)) return null;
  return full;
}

/**
 * Start the server on an ephemeral port.
 *
 * @param {{ port?: number }} [options]
 * @returns {Promise<{ origin: string, close: () => Promise<void> }>}
 */
export function startServer(options = {}) {
  /**
   * Requests per path.
   *
   * This is how SharedWorker uniqueness is observed *structurally* rather than
   * only behaviourally. One script URL means one instance per origin, and one
   * instance means the browser fetches the script once no matter how many tabs
   * call `new SharedWorker(url)`. Responses carry `cache-control: no-store`, so
   * a second instantiation is a second request and cannot hide in the cache.
   */
  const fetches = new Map();

  const server = createServer(async (req, res) => {
    const key = (req.url ?? '/').split('?')[0];
    fetches.set(key, (fetches.get(key) ?? 0) + 1);
    const path = resolveRequest(req.url ?? '/');
    if (!path) {
      res.writeHead(403).end('forbidden');
      return;
    }
    let info;
    try {
      info = await stat(path);
    } catch {
      res.writeHead(404).end('not found');
      return;
    }
    if (info.isDirectory()) {
      res.writeHead(404).end('not found');
      return;
    }
    const ext = extname(path);
    const type = TYPES.get(ext) ?? 'application/octet-stream';
    const headers = { 'content-type': type, 'cache-control': 'no-store' };
    if (ext === '.js' || ext === '.mjs') {
      const body = rewriteSpecifiers(await readFile(path, 'utf8'));
      res.writeHead(200, headers).end(body);
      return;
    }
    res.writeHead(200, { ...headers, 'content-length': String(info.size) });
    createReadStream(path).pipe(res);
  });

  return new Promise((ok, fail) => {
    server.once('error', fail);
    server.listen(options.port ?? 0, '127.0.0.1', () => {
      const { port } = server.address();
      ok({
        origin: `http://127.0.0.1:${port}`,
        fetches: (path) => fetches.get(path) ?? 0,
        resetFetches: () => fetches.clear(),
        close: () =>
          new Promise((done) => {
            server.closeAllConnections?.();
            server.close(() => done());
          }),
      });
    });
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { origin } = await startServer({ port: Number(process.argv[2]) || 8177 });
  console.log(`serving ${ROOT} at ${origin}`);
  console.log(`  manual page: ${origin}/test/browser.html`);
}
