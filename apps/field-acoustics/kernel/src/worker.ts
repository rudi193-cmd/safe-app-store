/**
 * Worker entry point.
 *
 * Spawn it as a module worker:
 *
 *     const w = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
 *
 * It also runs under `node:worker_threads`, which is how the test suite
 * exercises the protocol without a browser. The `node:` import sits inside a
 * branch that a browser never takes, and this package ships as raw ES modules
 * with no bundler, so nothing tries to resolve it there.
 */

import { WorkerCore } from './workerCore.js';
import type { WorkerRequest } from './protocol.js';

const core = new WorkerCore();
const g = globalThis as unknown as {
  onmessage?: (ev: MessageEvent) => void;
  postMessage?: (msg: unknown, transfer?: ArrayBufferLike[]) => void;
  process?: { versions?: { node?: string } };
};

function dispatch(msg: WorkerRequest, send: (r: unknown, t: ArrayBufferLike[]) => void): void {
  try {
    const { reply, transfer } = core.handle(msg);
    send(reply, transfer);
  } catch (err) {
    const e = err as Error;
    send(
      {
        type: 'error',
        batch: (msg as { batch?: number }).batch,
        message: e && e.message ? e.message : String(err),
        stack: e && e.stack ? e.stack : undefined,
      },
      [],
    );
  }
}

if (g.process?.versions?.node) {
  // Indirect specifier: keeps the TypeScript build free of a @types/node
  // dependency, and keeps browser bundlers from trying to resolve a node: URL.
  const spec = 'node:worker_threads';
  const wt = (await import(spec)) as {
    parentPort: {
      on(ev: string, fn: (msg: WorkerRequest) => void): void;
      postMessage(m: unknown, t?: unknown): void;
    } | null;
  };
  const parentPort = wt.parentPort;
  parentPort?.on('message', (msg: WorkerRequest) => {
    dispatch(msg, (reply, transfer) => parentPort.postMessage(reply, transfer));
  });
} else {
  g.onmessage = (ev: MessageEvent) => {
    dispatch(ev.data as WorkerRequest, (reply, transfer) =>
      (g.postMessage as (m: unknown, t: ArrayBufferLike[]) => void)(reply, transfer),
    );
  };
}
