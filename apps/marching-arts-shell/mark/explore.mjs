/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Build many marks from the same construction, put every one of them through
 * the same invariants, and draw them all on one sheet.
 *
 *   npm run explore           # table only
 *   npm run explore --sheet   # and a contact sheet PNG
 *
 * This is the playground half. Nothing here writes the shipped icon; output
 * goes to preview/, which is not committed. Its job is to find out which of
 * the invariants describe the construction and which only ever described the
 * dcisim mark, before either assumption travels to a repo that follows rules.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CANON, construct, raster } from './construct.mjs';
import { hasVerticalMirror, verdict } from './invariants.mjs';
import { crop, decodePng, encodePng } from './png.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const PREVIEW = resolve(here, 'preview');

export const VARIANTS = [
  ['canon', {}],
  ['N5 span2 — Reuleaux pentagon', { N: 5, span: 2 }],
  ['N7 span3 — Reuleaux heptagon', { N: 7, span: 3 }],
  ['N9 span4 — Reuleaux nonagon', { N: 9, span: 4 }],
  ['N4 span1', { N: 4, span: 1 }],
  ['N5 span1', { N: 5, span: 1 }],
  ['N6 span1', { N: 6, span: 1 }],
  ['N7 span2', { N: 7, span: 2 }],
  ['N5 span2, gap 0.5', { N: 5, span: 2, gapRatio: 0.5 }],
  ['gap 4 — wide', { gapRatio: 4 }],
  ['phase 0 — rotated', { phase: 0 }],
  ['phase 15 — off-axis', { phase: 15 }],
  ['dots R/12 — small', { sourceRatio: 12 }],
  ['dots R/4 — large', { sourceRatio: 4 }],
  ['stroke 0.5x dot', { strokeRatio: 0.5 }],
  ['clear space 2x', { clearRatio: 2 }],
  ['N4 span2 — degenerate', { N: 4, span: 2 }],
  ['gap 20 — over-trimmed', { gapRatio: 20 }],
];

export function evaluate(variants = VARIANTS) {
  return variants.map(([name, spec]) => {
    try {
      const geo = construct({ ...CANON, ...spec });
      return { name, spec, geo, ...verdict(geo), mirror: hasVerticalMirror(geo) };
    } catch (error) {
      return { name, spec, geo: null, refused: error.message };
    }
  });
}

/** Variant names carry slashes and em dashes; filenames should not. */
const slug = (name) => name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();

function sheet(rows, colours) {
  const cards = rows
    .map((row) => {
      const body = row.refused
        ? `<div class="refused">refused<br><span>${row.refused}</span></div>`
        : `<img src="${slug(row.name)}.svg" width="150" height="150">`;
      const status = row.refused
        ? ''
        : row.ok
          ? `<p class="ok">all ${row.applicable} applicable invariants hold</p>`
          : `<p class="bad">${row.failed.map((f) => f.name).join('<br>')}</p>`;
      const notes = row.refused || row.mirror ? '' : '<p class="note">no vertical mirror</p>';
      return `<figure>${body}<figcaption>${row.name}</figcaption>${status}${notes}</figure>`;
    })
    .join('\n');

  return `<!doctype html><meta charset="utf-8"><body>
<style>
  body { margin: 0; padding: 20px; background: ${colours.background}; font: 12px/1.45 system-ui, sans-serif; color: #4d5257; }
  .grid { display: grid; grid-template-columns: repeat(4, 190px); gap: 18px; }
  figure { margin: 0; }
  img { display: block; background: ${colours.background}; }
  figcaption { font-weight: 650; color: #1a1d20; margin-top: 4px; }
  p { margin: 2px 0 0; }
  .ok { color: #2c6e49; }
  .bad { color: #9b2226; }
  .note { color: #8a4b12; }
  .refused { width: 150px; height: 150px; display: flex; flex-direction: column; justify-content: center;
             text-align: center; color: #9b2226; border: 1px dashed #c4c0b3; box-sizing: border-box; padding: 8px; }
  .refused span { color: #767b80; font-size: 10px; }
</style>
<div class="grid">${cards}</div></body>`;
}

function render({ chrome, width, height }) {
  const shotPath = join(PREVIEW, 'shot.png');
  execFileSync(chrome, [
    '--headless',
    '--no-sandbox',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-color-profile=srgb',
    '--force-device-scale-factor=1',
    `--window-size=${width},${height + 400}`,
    `--screenshot=${shotPath}`,
    `file://${join(PREVIEW, 'sheet.html')}`,
  ], { stdio: ['ignore', 'ignore', 'ignore'] });
  const shot = decodePng(readFileSync(shotPath));
  writeFileSync(join(PREVIEW, 'sheet.png'), encodePng(crop(shot, width, Math.min(height, shot.height))));
  rmSync(shotPath, { force: true });
  return join(PREVIEW, 'sheet.png');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const rows = evaluate();

  for (const row of rows) {
    if (row.refused) {
      process.stdout.write(`refused  ${row.name.padEnd(30)} ${row.refused}\n`);
      continue;
    }
    const flag = row.ok ? 'holds  ' : 'BREAKS ';
    process.stdout.write(`${flag}  ${row.name.padEnd(30)} ${row.applicable} applicable\n`);
    for (const f of row.failed) process.stdout.write(`             ${f.name} — ${f.detail}\n`);
    if (!row.mirror) process.stdout.write('             (no vertical mirror: the raster gate does not apply)\n');
  }

  if (process.argv.includes('--sheet')) {
    if (!existsSync(PREVIEW)) mkdirSync(PREVIEW);
    const colours = { background: '#f6f5f2', foreground: '#8a5a10' };
    for (const row of rows) {
      if (row.geo) writeFileSync(join(PREVIEW, `${slug(row.name)}.svg`), raster(colours, row.geo));
    }
    writeFileSync(join(PREVIEW, 'sheet.html'), sheet(rows, colours));
    const chrome = process.env.CHROME ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
    const height = 40 + Math.ceil(rows.length / 4) * 235;
    process.stdout.write(`\nwrote ${render({ chrome, width: 860, height })}\n`);
  }
}
