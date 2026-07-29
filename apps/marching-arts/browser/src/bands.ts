/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Data-classification bands. Port of marching_arts/bands.py.
 *
 * The integers are the contract: they are written into the `band` column from
 * migration 001 and existing rows carry them. Do not reorder. The ordering is
 * load-bearing in two places — a grant names the highest band it authorizes and
 * covers everything below it, and `DERIVE_AT` is a `>=` comparison.
 *
 * This file is a transcription, not a design. If it disagrees with bands.py the
 * differential suite fails, and bands.py is right.
 */

/** L0 through L6, least to most sensitive. Mirrors `bands.Band`. */
export const Band = {
  SELF: 0,
  ROSTER: 1,
  CRAFT: 2,
  ACCOMMODATION: 3,
  HEALTH: 4,
  SAFEGUARDING: 5,
  FAMILY: 6,
} as const;

export type Band = (typeof Band)[keyof typeof Band];

/** Names in declaration order, so `parseBand` can accept a name like Python's `Band[...]`. */
export const BAND_NAMES = Object.keys(Band) as (keyof typeof Band)[];

/** Lowest and highest band integers — the CHECK bounds in migration 001. */
export const BAND_MIN: number = Math.min(...Object.values(Band));
export const BAND_MAX: number = Math.max(...Object.values(Band));

/**
 * At and above this band the platform serves the *derived instruction* and never
 * the underlying fact. Enforced as a projection in the SELECT list, not as a
 * promise in a doc — see `policy.Policy.projection`.
 */
export const DERIVE_AT: Band = Band.ACCOMMODATION;

/**
 * Bands this application refuses to serve at all, to anyone, under any grant.
 * Compiled into a DENY rule, so it negates the *union* of the allows and no
 * grant can win against it.
 */
export const NEVER_SERVED: ReadonlySet<Band> = new Set<Band>([Band.SAFEGUARDING]);

/**
 * Coerce a stored integer or a name to a Band, rejecting anything else.
 *
 * Fails loudly, exactly as `bands.parse` does. A band that cannot be resolved is
 * *not* defaulted to SELF: a silent downgrade to the least sensitive value is
 * the wrong failure direction for this column.
 */
export function parseBand(value: number | string | Band): Band {
  if (typeof value === 'number') {
    if (!Number.isInteger(value) || !(Object.values(Band) as number[]).includes(value)) {
      throw new RangeError(`${value} is not a valid Band`);
    }
    return value as Band;
  }
  if (typeof value === 'string') {
    const key = value.trim().toUpperCase() as keyof typeof Band;
    if (!(key in Band)) throw new RangeError(`${JSON.stringify(value)} is not a valid Band name`);
    return Band[key];
  }
  throw new TypeError(`cannot parse ${typeof value} as a Band`);
}

/** The DENY fragment's band list, rendered the way policy.py renders it. */
export function neverServedList(): string {
  return [...NEVER_SERVED].sort((a, b) => a - b).map((b) => String(b)).join(', ');
}
