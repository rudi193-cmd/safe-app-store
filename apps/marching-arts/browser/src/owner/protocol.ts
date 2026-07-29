/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The wire between a tab and the database owner.
 *
 * Deliberately tiny, and deliberately *not* a query builder. The only thing that
 * crosses this port is SQL the store composed plus a bag of bound parameters —
 * there is no message that says "give me the rows for principal X" and no
 * message that returns rows for the client to filter. The predicate is compiled
 * on the calling side and travels *with* the statement, so the owner cannot
 * accidentally answer an unauthorized question: it never knows what the question
 * was about.
 *
 * Everything here is structured-clone-safe by construction; there are no
 * functions, no class instances and no transferables in either direction.
 */

import type { Params } from '../rules.js';

export const PROTOCOL_VERSION = 1;

export type Op = 'all' | 'get' | 'run' | 'exec' | 'begin' | 'commit' | 'rollback' | 'close';

export interface Request {
  readonly v: number;
  readonly id: number;
  readonly op: Op;
  readonly sql?: string;
  readonly params?: Params;
}

export interface ErrorShape {
  readonly name: string;
  readonly message: string;
  /** SQLite extended result code where the failure came from SQLite. */
  readonly code?: number;
}

export type Response =
  | { readonly v: number; readonly id: number; readonly ok: true; readonly value: unknown }
  | { readonly v: number; readonly id: number; readonly ok: false; readonly error: ErrorShape };

/** Unsolicited notices the owner pushes to every attached port. */
export interface Notice {
  readonly v: number;
  readonly notice: 'ready' | 'paused' | 'resumed' | 'lost';
  readonly vfs?: string;
  readonly durable?: boolean;
  readonly notes?: readonly string[];
  readonly reason?: string;
}

export type Outbound = Response | Notice;

export function isNotice(m: Outbound): m is Notice {
  return typeof (m as Notice).notice === 'string';
}

export function toErrorShape(error: unknown): ErrorShape {
  if (error && typeof error === 'object') {
    const e = error as { name?: unknown; message?: unknown; resultCode?: unknown };
    const shape: { name: string; message: string; code?: number } = {
      name: typeof e.name === 'string' ? e.name : 'Error',
      message: typeof e.message === 'string' ? e.message : String(error),
    };
    if (typeof e.resultCode === 'number') shape.code = e.resultCode;
    return shape;
  }
  return { name: 'Error', message: String(error) };
}

/** Rebuild a throwable from the wire shape, keeping the SQLite result code. */
export function fromErrorShape(shape: ErrorShape): Error {
  const error = new Error(shape.message) as Error & { resultCode?: number };
  error.name = shape.name;
  if (shape.code !== undefined) error.resultCode = shape.code;
  return error;
}
