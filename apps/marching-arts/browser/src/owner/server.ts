/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The owner side of the port: dispatch a `Request` against a `Connection`.
 *
 * `handleRequest` is a pure function of (connection, request). That is on
 * purpose — it is the only part of the SharedWorker story Node can execute, and
 * `test/owner.mjs` drives it over a real MessageChannel against a real
 * SQLite-WASM connection. The parts Node cannot reach (Web Locks election, SAH
 * pool pause/resume) are isolated in `election.ts` and `../open.ts` rather than
 * mixed in here where the distinction would blur; they are gated separately, in
 * a browser, by `test/browser-gate.mjs`.
 *
 * One thing here is neither: a request arriving before `getConnection()` returns
 * a connection is answered with a hard `OwnerUnavailable` rather than queued, so
 * a tab that issues SQL the moment its port exists races the owner's lock
 * acquisition and loses on a cold start. `ready` is the documented signal that
 * the owner is serving and callers are expected to wait for it. Whether this
 * should queue instead is a protocol decision — it would also change what
 * happens to in-flight requests *during* a handoff — and is listed as uncovered
 * in README.md rather than quietly changed.
 */

import type { Connection } from '../connection.js';
import {
  PROTOCOL_VERSION,
  type Notice,
  type Request,
  type Response,
  toErrorShape,
} from './protocol.js';

/** Anything with `postMessage` and `addEventListener('message')`. */
export interface PortLike {
  postMessage(message: unknown): void;
  addEventListener(type: 'message', listener: (event: { data: unknown }) => void): void;
  start?(): void;
  close?(): void;
}

export async function handleRequest(conn: Connection, req: Request): Promise<Response> {
  try {
    let value: unknown;
    switch (req.op) {
      case 'all':
        value = await conn.all(req.sql as string, req.params);
        break;
      case 'get': {
        const row = await conn.get(req.sql as string, req.params);
        value = row === undefined ? null : row;
        break;
      }
      case 'run':
        value = await conn.run(req.sql as string, req.params);
        break;
      case 'exec':
        await conn.exec(req.sql as string);
        value = null;
        break;
      case 'begin':
        await conn.begin();
        value = null;
        break;
      case 'commit':
        await conn.commit();
        value = null;
        break;
      case 'rollback':
        await conn.rollback();
        value = null;
        break;
      case 'close':
        await conn.close();
        value = null;
        break;
      default:
        throw new Error(`unknown op ${JSON.stringify((req as Request).op)}`);
    }
    return { v: PROTOCOL_VERSION, id: req.id, ok: true, value };
  } catch (error) {
    return { v: PROTOCOL_VERSION, id: req.id, ok: false, error: toErrorShape(error) };
  }
}

/**
 * Attach a port to a connection, serialising requests.
 *
 * Requests are queued rather than interleaved: `oo1` is synchronous inside the
 * worker, and two overlapping explicit transactions from two tabs would be a
 * correctness bug, not a throughput opportunity.
 */
export function serve(
  port: PortLike,
  getConnection: () => Connection | null,
): { readonly idle: () => Promise<void> } {
  let chain: Promise<unknown> = Promise.resolve();

  port.addEventListener('message', (event) => {
    const req = event.data as Request;
    if (!req || typeof req.id !== 'number') return;
    chain = chain.then(async () => {
      const conn = getConnection();
      if (!conn) {
        port.postMessage({
          v: PROTOCOL_VERSION,
          id: req.id,
          ok: false,
          error: { name: 'OwnerUnavailable', message: 'the database owner is not open' },
        } satisfies Response);
        return;
      }
      port.postMessage(await handleRequest(conn, req));
    });
  });
  port.start?.();

  return { idle: () => chain.then(() => undefined) };
}

export function announce(ports: Iterable<PortLike>, notice: Omit<Notice, 'v'>): void {
  for (const port of ports) port.postMessage({ v: PROTOCOL_VERSION, ...notice } satisfies Notice);
}
