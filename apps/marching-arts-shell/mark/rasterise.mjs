/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Rasterises icon-touch.svg to assets/icon-192.png, which index.html hands to
 * apple-touch-icon. Kept out of build.mjs because it needs a browser, and a
 * build step that cannot run everywhere should not be the one that decides
 * whether the SVGs are up to date.
 *
 *   node app/assets/logo/rasterise.mjs [--chrome /path/to/chrome]
 *
 * The PNG's bytes are not reproducible across Chromium versions, so nothing
 * byte-compares it. What construct.test.mjs does check is in test-png.mjs;
 * what it cannot check is stated in README.md.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, writeFileSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { crop, decodePng, encodePng, pixelAt } from './png.mjs';
import { CANON, construct, raster as rasterSvg } from './construct.mjs';

const here = dirname(fileURLToPath(import.meta.url));

export const RASTER = Object.freeze({
  size: 192,
  source: resolve(here, 'icon-touch.svg'),
  out: resolve(here, '../web/assets/icon-192.png'),
});

/**
 * The icon set, and nothing beyond it. Six files is the current minimum a PWA
 * actually needs; the thirty-file mstile-and-every-Android-density matrices most
 * generators still emit are pre-2020 cargo cult.
 *
 * `maskable` is not a hand-padded copy of the mark. Android masks to a circle of
 * 80% diameter, and the mark's ink reaches R + source = 28 of a 32 half-box —
 * 87.5%, which would clip. Rebuilding at clearRatio 2 puts it at 28/36 = 77.8%,
 * inside the safe zone, and that spec passes every gate in invariants.mjs
 * unchanged. The safe zone is met by construction rather than by eye.
 */
export const ICON_SET = Object.freeze([
  { file: 'icon-192.png', size: 192, spec: {} },
  { file: 'icon-512.png', size: 512, spec: {} },
  { file: 'icon-512-maskable.png', size: 512, spec: { clearRatio: 2 } },
  { file: 'apple-touch-icon.png', size: 180, spec: {} },
]);

const CANDIDATES = [
  process.env.CHROME,
  '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  '/usr/bin/chromium',
  '/usr/bin/google-chrome',
];

export function findChrome(explicit) {
  const tried = [explicit, ...CANDIDATES].filter(Boolean);
  const found = tried.find((p) => existsSync(p));
  if (!found) {
    throw new Error(`no Chromium found. Tried:\n  ${tried.join('\n  ')}\nPass --chrome <path>.`);
  }
  return found;
}

/**
 * Headroom added to the requested window height. This build of headless
 * Chromium still subtracts window chrome from the viewport while screenshotting
 * the whole window, so asking for a 192-tall window yields 192 rows of which
 * only ~105 are the page and the rest are white. Asking for far more and
 * cropping the top-left corner is correct whether or not a given build does
 * that, which a tuned offset would not be.
 */
const HEADROOM = 400;

/**
 * Refuse to write a wrong icon. The mark's own background rect covers the full
 * crop, so any corner landing on page white means the viewport was smaller than
 * the icon and the crop caught the page instead.
 *
 * Exported because it is the only part of this module that can be gated without
 * a browser, and it went unexercised for as long as it lived inline: the
 * condition it guards needs a viewport too small to induce on demand — asking
 * Chromium for a 4096px icon just produces a 4096px icon.
 */
export function assertCropCaughtTheIcon(image, size) {
  for (const [x, y] of [[0, 0], [size - 1, 0], [0, size - 1], [size - 1, size - 1]]) {
    const px = pixelAt(image, x, y);
    if (px[0] === 255 && px[1] === 255 && px[2] === 255) {
      throw new Error(`corner ${x},${y} is page white: viewport smaller than ${size}px`);
    }
  }
}

export function rasterise({ chrome, size = RASTER.size, source = RASTER.source, out = RASTER.out }) {
  const work = mkdtempSync(join(tmpdir(), 'dcisim-logo-'));
  try {
    copyFileSync(source, join(work, 'mark.svg'));
    writeFileSync(
      join(work, 'page.html'),
      `<!doctype html><meta charset="utf-8">` +
        `<body style="margin:0">` +
        // display:block, or the image sits on a text baseline and leaves a
        // strip of page showing along the bottom of every icon we ship.
        `<img style="display:block" src="mark.svg" width="${size}" height="${size}"></body>\n`,
    );
    execFileSync(chrome, [
      '--headless',
      '--no-sandbox',
      '--disable-gpu',
      '--hide-scrollbars',
      '--force-color-profile=srgb',
      '--force-device-scale-factor=1',
      `--window-size=${size},${size + HEADROOM}`,
      `--screenshot=${join(work, 'shot.png')}`,
      `file://${join(work, 'page.html')}`,
    ], { stdio: ['ignore', 'ignore', 'ignore'] });

    const shot = decodePng(readFileSync(join(work, 'shot.png')));
    const image = crop(shot, size, size);
    assertCropCaughtTheIcon(image, size);
    const png = encodePng(image);
    writeFileSync(out, png);
    return png;
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
}

/** Writes every entry in ICON_SET. Each is generated, none is a resized copy. */
export function rasteriseSet({ chrome, colours, dir }) {
  const written = [];
  for (const entry of ICON_SET) {
    const geo = construct({ ...CANON, ...entry.spec });
    const svg = join(dir, `.${entry.file}.svg`);
    writeFileSync(svg, rasterSvg(colours, geo));
    try {
      const png = rasterise({ chrome, size: entry.size, source: svg, out: join(dir, entry.file) });
      written.push({ ...entry, bytes: png.length });
    } finally {
      rmSync(svg, { force: true });
    }
  }
  return written;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const flag = process.argv.indexOf('--chrome');
  const chrome = findChrome(flag === -1 ? undefined : process.argv[flag + 1]);
  const { rasterColours } = await import('./build.mjs');
  const dir = dirname(RASTER.out);
  for (const w of rasteriseSet({ chrome, colours: rasterColours(), dir })) {
    process.stdout.write(`wrote ${w.file} (${w.size}px, ${w.bytes} bytes)\n`);
  }
}
