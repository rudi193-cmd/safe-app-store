/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Opening the database file, and being honest about where it landed.
 *
 * The ladder, in order of preference:
 *
 *   1. `opfs-sahpool` — the target. Synchronous access handles over a pool of
 *      pre-created OPFS files. Fastest of the OPFS VFSes, needs no COOP/COEP
 *      headers, and takes exclusive handles, which is why the SharedWorker owner
 *      and the Web Lock in `owner/election.ts` exist.
 *   2. memory — a session-lifetime database. Correct, and durable in no sense
 *      whatsoever.
 *
 * There is no silent step. Every rung reports what it is and whether it is
 * durable, and a shell that does not surface `durable === false` is lying to a
 * user about whether their data survives the tab. That reporting shape is lifted
 * from quick-stupids' `app/src/storage/index.js`, which got it right: a backend
 * seam with an ordered ladder and a `notes[]` explaining every rung it skipped.
 */

import sqlite3InitModule from '@sqlite.org/sqlite-wasm';

import { Oo1Connection } from './sqlite.js';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Sqlite3 = any;

export type Vfs = 'opfs-sahpool' | 'memory';

export interface OpenResult {
  readonly conn: Oo1Connection;
  readonly vfs: Vfs;
  readonly durable: boolean;
  readonly notes: readonly string[];
  /**
   * Release the VFS's file handles without losing the pool, so another context
   * may take ownership. Only meaningful on `opfs-sahpool`.
   */
  pause(): Promise<void>;
  /** Retake the handles after a `pause()`. */
  unpause(): Promise<void>;
  close(): Promise<void>;
}

export interface OpenOptions {
  /** Database filename inside the VFS. */
  filename?: string;
  /** SAH pool name. Two apps on one origin must not share a pool. */
  poolName?: string;
  /** Initial pool capacity. Grows on demand; each slot is one OPFS file. */
  initialCapacity?: number;
  /** Skip OPFS entirely. The differential suite sets this under Node. */
  forceMemory?: boolean;
}

let initialised: Promise<Sqlite3> | null = null;

/**
 * Initialise the WASM module once per context.
 *
 * The shipped `.d.mts` types `init()` as taking no arguments, but the runtime
 * accepts an Emscripten module object; the cast is to pass `print`/`printErr` so
 * a page's console is not filled by the library's banner.
 */
export function sqlite3(): Promise<Sqlite3> {
  if (!initialised) {
    const init = sqlite3InitModule as unknown as (opts?: object) => Promise<Sqlite3>;
    initialised = init({ print: () => {}, printErr: () => {} });
  }
  return initialised;
}

export async function openDatabase(options: OpenOptions = {}): Promise<OpenResult> {
  const filename = options.filename ?? '/marching-arts.sqlite3';
  const poolName = options.poolName ?? 'marching-arts-pool';
  const api = await sqlite3();
  const notes: string[] = [];

  if (!options.forceMemory && typeof api.installOpfsSAHPoolVfs === 'function') {
    try {
      const pool = await api.installOpfsSAHPoolVfs({
        name: poolName,
        initialCapacity: options.initialCapacity ?? 8,
        clearOnInit: false,
      });
      const db = new pool.OpfsSAHPoolDb(filename);
      db.exec('PRAGMA foreign_keys = ON');
      const conn = new Oo1Connection(api, db);
      return {
        conn,
        vfs: 'opfs-sahpool',
        durable: true,
        notes,
        pause: async () => {
          pool.pauseVfs();
        },
        unpause: async () => {
          await pool.unpauseVfs();
        },
        close: async () => {
          db.close();
        },
      };
    } catch (error) {
      notes.push(`opfs-sahpool unavailable: ${(error as Error).message}`);
    }
  } else if (!options.forceMemory) {
    notes.push('opfs-sahpool unavailable: this build exposes no installOpfsSAHPoolVfs');
  }

  if (!options.forceMemory) {
    notes.push(
      'Falling back to an in-memory database: everything written is lost when this context ends.',
    );
  }
  const db = new api.oo1.DB(':memory:', 'c');
  db.exec('PRAGMA foreign_keys = ON');
  const conn = new Oo1Connection(api, db);
  return {
    conn,
    vfs: 'memory',
    durable: false,
    notes,
    pause: async () => {},
    unpause: async () => {},
    close: async () => {
      db.close();
    },
  };
}
