// Assemble www/ for Capacitor.
//
// The app has no build step to *run* — index.html loads plain ES modules and
// works off any static server. But Capacitor copies a single directory into
// the native project, and that directory must not contain node_modules, the
// test harness, or the Android project itself. So packaging is a copy of the
// four things the app actually needs, and nothing else.
//
// Deliberately a whitelist rather than an ignore list. An ignore list quietly
// ships whatever you forget to exclude, and the thing most likely to be
// forgotten here is a directory holding an API key or a build artifact.

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'www');

const INCLUDE = ['index.html', 'styles.css', 'src', 'vendor'];

async function copy(from, to) {
  const stat = await fs.stat(from);
  if (stat.isDirectory()) {
    await fs.mkdir(to, { recursive: true });
    for (const entry of await fs.readdir(from)) {
      // vendor/entry.js is the esbuild input, not something the browser loads.
      if (entry === 'entry.js') continue;
      await copy(path.join(from, entry), path.join(to, entry));
    }
    return;
  }
  await fs.copyFile(from, to);
}

await fs.rm(OUT, { recursive: true, force: true });
await fs.mkdir(OUT, { recursive: true });

for (const item of INCLUDE) {
  await copy(path.join(ROOT, item), path.join(OUT, item));
}

// Fail loudly rather than hand Capacitor a directory that is missing the app.
const required = ['index.html', 'src/app.js', 'vendor/anthropic.js'];
for (const rel of required) {
  try {
    await fs.access(path.join(OUT, rel));
  } catch {
    console.error(`build-www: ${rel} missing from www/ — the packaged app would not start`);
    process.exit(1);
  }
}

const count = (await fs.readdir(path.join(OUT, 'src'))).length;
console.log(`www/ built: index.html, styles.css, ${count} modules, vendor/anthropic.js`);
