/**
 * Instrument definitions: radiated power spectrum, bell geometry, aim.
 * Port of `dcisim/instruments.py`.
 *
 * Sound power levels are per player at a sustained fortissimo, dB re 1 pW per
 * octave band. They are representative rather than measured — calibrated so a
 * full corps lands around 95-100 dBA in the low rows at typical stadium
 * distances. Treat them as a starting point and override them if you have data.
 *
 * `bellAzimuthOffsetDeg` is the angle between the player's facing direction and
 * the bell axis. Everything in a hornline is zero. Marching bass drums are the
 * interesting exception: the heads face left and right, so a bass drum radiates
 * perpendicular to the way its player is facing.
 */

import { N_BANDS } from './atmosphere.js';
import { DEFAULT_FRONT_TO_BACK, DEFAULT_SIDELOBE_FLOOR, Directivity } from './directivity.js';

export class Instrument {
  readonly name: string;
  /** Sound power level per octave band, dB re 1 pW. */
  powerDb: number[];
  /** PHYSICAL bell/head radius; `directivity.ts` applies its own aperture fit. */
  bellRadiusM: number;
  /** Height of the bell above the field surface, metres. */
  bellHeightM: number;
  /** Positive tips the bell up ("horns up"). */
  bellElevationDeg: number;
  /** Bell axis relative to facing. */
  bellAzimuthOffsetDeg: number;
  frontToBack: number[];

  private cache = new Map<string, Directivity>();
  private measured: { table: Float64Array; theta?: Float64Array } | null = null;
  private measuredCitation = '';

  constructor(init: {
    name: string;
    powerDb: number[];
    bellRadiusM: number;
    bellHeightM: number;
    bellElevationDeg?: number;
    bellAzimuthOffsetDeg?: number;
    frontToBack?: number[];
  }) {
    if (init.powerDb.length !== N_BANDS) {
      throw new RangeError(`${init.name}: powerDb needs ${N_BANDS} values`);
    }
    this.name = init.name;
    this.powerDb = init.powerDb.slice();
    this.bellRadiusM = init.bellRadiusM;
    this.bellHeightM = init.bellHeightM;
    this.bellElevationDeg = init.bellElevationDeg ?? 0.0;
    this.bellAzimuthOffsetDeg = init.bellAzimuthOffsetDeg ?? 0.0;
    // A copy, not the shared module-level array: otherwise every brass
    // instrument holds the same object and retuning one retunes all four.
    this.frontToBack = (init.frontToBack ?? DEFAULT_FRONT_TO_BACK).slice();
  }

  /**
   * Replace the fitted directivity with measured data. A citation is required
   * rather than optional: measured data nobody can look up is not meaningfully
   * better than a fitted curve.
   */
  setMeasured(table: ArrayLike<number>, citation: string, theta?: ArrayLike<number>): this {
    if (!citation || !String(citation).trim()) {
      throw new RangeError(
        'measured directivity needs a citation — the point of using it is that ' +
          'someone can check where it came from',
      );
    }
    this.measured = {
      table: Float64Array.from(table),
      theta: theta ? Float64Array.from(theta) : undefined,
    };
    this.measuredCitation = String(citation).trim();
    this.cache.clear();
    return this;
  }

  clearMeasured(): this {
    this.measured = null;
    this.measuredCitation = '';
    this.cache.clear();
    return this;
  }

  get citation(): string {
    return this.measuredCitation;
  }

  get isMeasured(): boolean {
    return this.measured !== null;
  }

  /**
   * Cache key covers everything the table is built from, not just temperature:
   * these are module-level singletons and callers are invited to override them,
   * so a narrower key would silently serve the old physics after an edit.
   */
  directivity(tempC = 24.0): Directivity {
    if (this.measured) {
      let d = this.cache.get('measured');
      if (!d) {
        d = Directivity.fromMeasured(this.measured.table, this.measured.theta);
        this.cache.set('measured', d);
      }
      return d;
    }
    const key = `${tempC.toFixed(3)}|${this.bellRadiusM}|${this.frontToBack.join(',')}`;
    let d = this.cache.get(key);
    if (!d) {
      d = new Directivity(this.bellRadiusM, this.frontToBack, DEFAULT_SIDELOBE_FLOOR, tempC);
      this.cache.set(key, d);
    }
    return d;
  }
}

const percFtb = () => [1.0, 1.5, 2.5, 4.0, 6.0, 8.0, 10.0, 12.0];

//                                   63   125   250   500    1k    2k    4k    8k
export const TRUMPET = new Instrument({
  name: 'trumpet',
  powerDb: [84, 94, 102, 109, 111, 109, 104, 96],
  bellRadiusM: 0.062,
  bellHeightM: 1.6,
  bellElevationDeg: 8.0,
});
export const MELLOPHONE = new Instrument({
  name: 'mellophone',
  powerDb: [86, 98, 106, 110, 109, 105, 99, 90],
  bellRadiusM: 0.13,
  bellHeightM: 1.55,
  bellElevationDeg: 6.0,
});
export const BARITONE = new Instrument({
  name: 'baritone',
  powerDb: [92, 103, 109, 110, 107, 102, 96, 87],
  bellRadiusM: 0.14,
  bellHeightM: 1.58,
  bellElevationDeg: 5.0,
});
export const CONTRA = new Instrument({
  name: 'contra',
  powerDb: [104, 110, 111, 108, 103, 97, 90, 81],
  bellRadiusM: 0.24,
  bellHeightM: 1.85,
  bellElevationDeg: 4.0,
});

// Carry angles matter more than they look. A modern marching snare is carried
// with the head close to horizontal, so its radiating axis is nearly vertical
// and turning the player barely changes what the audience receives.
export const SNARE = new Instrument({
  name: 'snare',
  powerDb: [86, 94, 101, 106, 109, 111, 111, 107],
  bellRadiusM: 0.171,
  bellHeightM: 0.95,
  bellElevationDeg: 80.0,
  frontToBack: percFtb(),
});
export const TENOR = new Instrument({
  name: 'tenor',
  powerDb: [94, 102, 107, 108, 107, 105, 102, 97],
  bellRadiusM: 0.14,
  bellHeightM: 0.95,
  bellElevationDeg: 72.0,
  frontToBack: percFtb(),
});
export const BASS = new Instrument({
  name: 'bass',
  powerDb: [110, 112, 108, 103, 98, 93, 88, 82],
  bellRadiusM: 0.33,
  bellHeightM: 1.0,
  bellElevationDeg: 0.0,
  bellAzimuthOffsetDeg: 90.0, // heads face sideways, not forward
  frontToBack: percFtb(),
});

// Front ensemble is amplified through a front-sideline PA, so it always fires
// into the house regardless of what the drill does. NOTE: this is eight
// acoustic point sources on the sideline, not a real PA model — see the
// limitations section of the README before reading anything into it.
export const PIT = new Instrument({
  name: 'pit',
  powerDb: [100, 106, 108, 108, 107, 105, 102, 96],
  bellRadiusM: 0.1,
  bellHeightM: 1.8,
  bellElevationDeg: 0.0,
  frontToBack: [3, 4, 6, 9, 12, 14, 16, 18],
});

export const CATALOG = new Map<string, Instrument>(
  [TRUMPET, MELLOPHONE, BARITONE, CONTRA, SNARE, TENOR, BASS, PIT].map((i) => [i.name, i]),
);
