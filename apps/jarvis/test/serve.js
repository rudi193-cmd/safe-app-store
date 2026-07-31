// Static server for local use: `npm run serve`, then open the printed URL.
// ES modules do not load over file://, so the app needs a server even though
// it has no backend.

import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT || 8080);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
};

http
  .createServer(async (req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
    const abs = path.join(ROOT, rel);
    if (!abs.startsWith(ROOT)) {
      res.writeHead(403).end('no');
      return;
    }
    try {
      const body = await fs.readFile(abs);
      res
        .writeHead(200, {
          'content-type': TYPES[path.extname(abs)] || 'application/octet-stream',
          'cache-control': 'no-store',
        })
        .end(body);
    } catch {
      res.writeHead(404).end('not found');
    }
  })
  .listen(PORT, () => {
    console.log(`jarvis on http://localhost:${PORT}/`);
    console.log('Speech input needs Chrome or Safari. Add an API key in settings.');
  });
