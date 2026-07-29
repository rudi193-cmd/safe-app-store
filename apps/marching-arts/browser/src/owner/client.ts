/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * A `Connection` that lives on the other end of a MessagePort.
 *
 * This is what a tab holds. It is the same interface `Oo1Connection` implements,
 * so `Store` does not know or care which one it has, and there is exactly one
 * copy of the predicate logic in the codebase regardless of where the file is.
 */

import type { Connection, Row, RunResult } from '../connection.js';
import type { Params } from '../rules.js';
import {
  PROTOCOL_VERSION,
  fromErrorShape,
  isNotice,
  type Notice,
  type Op,
  type Outbound,
  type Request,
} from './protocol.js';
import type { PortLike } from './server.js';

export class RemoteConnection implements Connection {
  private readonly port: PortLike;
  private nextId = 1;
  private readonly pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: unknown) => void }
  >();

  /** Latest owner notice, so a shell can render "memory only, not durable". */
  status: Notice | null = null;
  onNotice: ((notice: Notice) => void) | null = null;

  constructor(port: PortLike) {
    this.port = port;
    port.addEventListener('message', (event) => {
      const message = event.data as Outbound;
      if (!message || typeof message !== 'object') return;
      if (isNotice(message)) {
        this.status = message;
        this.onNotice?.(message);
        return;
      }
      const waiter = this.pending.get(message.id);
      if (!waiter) return;
      this.pending.delete(message.id);
      if (message.ok) waiter.resolve(message.value);
      else waiter.reject(fromErrorShape(message.error));
    });
    port.start?.();
  }

  private call(op: Op, sql?: string, params?: Params): Promise<unknown> {
    const id = this.nextId++;
    const request: Request = { v: PROTOCOL_VERSION, id, op, sql, params };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.port.postMessage(request);
    });
  }

  async all(sql: string, params?: Params): Promise<Row[]> {
    return (await this.call('all', sql, params)) as Row[];
  }

  async get(sql: string, params?: Params): Promise<Row | undefined> {
    const row = (await this.call('get', sql, params)) as Row | null;
    return row === null ? undefined : row;
  }

  async run(sql: string, params?: Params): Promise<RunResult> {
    return (await this.call('run', sql, params)) as RunResult;
  }

  async exec(sql: string): Promise<void> {
    await this.call('exec', sql);
  }

  async begin(): Promise<void> {
    await this.call('begin');
  }

  async commit(): Promise<void> {
    await this.call('commit');
  }

  async rollback(): Promise<void> {
    await this.call('rollback');
  }

  /**
   * Detach this tab. The owner stays open for the other tabs — closing a
   * *client* must never close the database, or the last tab to be refreshed
   * would take everyone else's connection with it.
   */
  async close(): Promise<void> {
    for (const [, waiter] of this.pending) {
      waiter.reject(new Error('connection closed'));
    }
    this.pending.clear();
    this.port.close?.();
  }
}
