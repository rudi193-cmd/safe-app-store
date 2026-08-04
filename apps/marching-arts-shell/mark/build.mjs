/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Writes every drawn form of the mark from construct.mjs, and splices the
 * inline glyph into index.html so the app bar and the icon file cannot drift
 * apart. Run it, then run construct.test.mjs, which fails if the files on disk
 * are not what this script would produce.
 *
 *   npm run build   # from apps/marching-arts-shell
 *
 * The PNG is the exception and is not written here; see rasterise.mjs.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { glyph, icon, raster } from './construct.mjs';

const here = dirname(fileURLToPath(import.meta.url));
export const PATHS = {
  tokens: resolve(here, '../web/styles/tokens.css'),
  icon: resolve(here, '../web/assets/icon.svg'),
  touch: resolve(here, 'icon-touch.svg'),
  index: resolve(here, '../web/index.html'),
};

/**
 * The mark's colour is not the mark's decision. Both values come from
 * tokens.css, and the dark value has to be stated identically by the media
 * query and the pinned selector or there is nothing to read.
 */
export function accents(css = readFileSync(PATHS.tokens, 'utf8')) {
  const found = [...css.matchAll(/--accent:\s*(#[0-9a-fA-F]{3,8})\s*;/g)].map((m) => m[1]);
  if (found.length < 2) {
    throw new Error(`tokens.css: expected a light and a dark --accent, found ${found.length}`);
  }
  const [light, ...darks] = found;
  const disagree = darks.filter((d) => d !== darks[0]);
  if (disagree.length > 0) {
    throw new Error(`tokens.css: dark --accent stated more than one way: ${darks.join(', ')}`);
  }
  return { light, dark: darks[0] };
}

/** Light surface, because a touch icon is composited onto black otherwise. */
export function rasterColours(css = readFileSync(PATHS.tokens, 'utf8')) {
  const bg = /--bg:\s*(#[0-9a-fA-F]{3,8})\s*;/.exec(css);
  if (!bg) throw new Error('tokens.css: no --bg found');
  return { background: bg[1], foreground: accents(css).light };
}

const GLYPH_BLOCK = /^[ \t]*<svg class="wordmark-glyph"[\s\S]*?<\/svg>$/m;

export function spliceGlyph(html) {
  const match = GLYPH_BLOCK.exec(html);
  if (!match) throw new Error('index.html: no <svg class="wordmark-glyph"> block to replace');
  const indent = /^[ \t]*/.exec(match[0])[0];
  return html.replace(GLYPH_BLOCK, glyph(indent));
}

export function outputs() {
  const css = readFileSync(PATHS.tokens, 'utf8');
  return {
    [PATHS.icon]: icon(accents(css)),
    [PATHS.touch]: raster(rasterColours(css)),
    [PATHS.index]: spliceGlyph(readFileSync(PATHS.index, 'utf8')),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  for (const [path, content] of Object.entries(outputs())) {
    writeFileSync(path, content);
    process.stdout.write(`wrote ${path}\n`);
  }
}
