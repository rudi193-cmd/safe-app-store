/*
 * Copyright 2026 The dcisim Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * PNG read/write for the raster gates, plus the small pixel helpers they use.
 *
 * The decoder and encoder here were hand-written — zlib inflate, the five row
 * filters, CRC32, IHDR/IDAT/IEND — and are now pngjs (MIT), which is tested
 * against the PNG suite and handles every colour type rather than the two we
 * happened to need. That last part is a real gain and not just less code: the
 * old decoder threw on anything but 8-bit truecolour, so a Chromium build that
 * emitted a palette or 16-bit screenshot would have failed the gate for a
 * reason that had nothing to do with the mark.
 *
 * pngjs normalises everything to 8-bit RGBA on read, so `channels` is always 4
 * here regardless of what was on disk.
 */

import { PNG } from 'pngjs';

/** @returns {{width:number,height:number,channels:number,pixels:Uint8Array}} */
export function decodePng(buffer) {
  const png = PNG.sync.read(buffer);
  return { width: png.width, height: png.height, channels: 4, pixels: png.data };
}

/**
 * Encoder settings, stated rather than defaulted. pngjs's defaults are tuned
 * for photographic content — adaptive per-row filtering with the Z_RLE deflate
 * strategy — and on a flat two-colour mark they cost 48% (6,182 bytes against
 * 4,178). Switching the library in silently inflated the shipped icon by half
 * and every one of the 22 gates still passed, because none of them looked at
 * how big the artefact was. See the byte-budget gate in construct.test.mjs.
 *
 * colorType 2 drops the alpha channel, which the touch icon does not use: it
 * paints an opaque background rect precisely because iOS composites alpha onto
 * black. filterType 0 (None) beats adaptive filtering on large flat runs, and
 * deflateStrategy 0 (default) beats Z_RLE once the rows are unfiltered.
 */
const ENCODE = { colorType: 2, filterType: 0, deflateLevel: 9, deflateStrategy: 0 };

export function encodePng({ width, height, pixels }) {
  const png = new PNG({ width, height });
  png.data = Buffer.from(pixels.buffer ?? pixels, pixels.byteOffset ?? 0, pixels.length);
  return PNG.sync.write(png, ENCODE);
}

/** Top-left crop. The rasteriser needs it; see rasterise.mjs for why. */
export function crop(image, width, height) {
  if (width > image.width || height > image.height) throw new Error('crop is larger than image');
  const out = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    const from = y * image.width * image.channels;
    const to = y * width * 4;
    for (let x = 0; x < width; x += 1) {
      const i = from + x * image.channels;
      const j = to + x * 4;
      out[j] = image.pixels[i];
      out[j + 1] = image.pixels[i + 1];
      out[j + 2] = image.pixels[i + 2];
      out[j + 3] = image.channels === 4 ? image.pixels[i + 3] : 255;
    }
  }
  return { width, height, channels: 4, pixels: out };
}

export function pixelAt(image, x, y) {
  const i = (y * image.width + x) * image.channels;
  return [image.pixels[i], image.pixels[i + 1], image.pixels[i + 2]];
}

export function rgb(hex) {
  const h = hex.replace('#', '');
  return [0, 1, 2].map((i) => parseInt(h.slice(i * 2, i * 2 + 2), 16));
}

/** Euclidean distance in raw sRGB. Crude, and only ever used with wide bands. */
export function distance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}
