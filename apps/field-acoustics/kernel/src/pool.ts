/**
 * A worker pool for computing a whole show off the main thread.
 *
 * No `SharedArrayBuffer`, no COOP/COEP, no cross-origin isolation. Each worker
 * computes into private buffers and transfers them back. See `protocol.ts` for
 * why that is sufficient here.
 *
 * Works in a browser (`Worker`) and under Node (`node:worker_threads`), which is
 * how the test suite exercises it. Supply your own `spawn` to use anything else.
 */

import type { SimJob, SimJobResult, WorkerReply, WorkerRequest } from './protocol.js';

export interface PoolWorker {
  post(msg: WorkerRequest, transfer: ArrayBufferLike[]): void;
  onMessage(fn: (msg: WorkerReply) => void): void;
  onError(fn: (err: Error) => void): void;
  terminate(): void | Promise<void>;
}

export type SpawnFn = (url: URL) => PoolWorker | Promise<PoolWorker>;

export interface WorkerPoolOptions {
  /** Defaults to `navigator.hardwareConcurrency` (capped at 8), else 4. */
  size?: number;
  /** Defaults to `new URL('./worker.js', import.meta.url)`. */
  workerUrl?: URL;
  spawn?: SpawnFn;
  /**
   * Jobs per `postMessage`. The spike measured dispatch overhead as significant
   * against a ~25 ms task, so batching several sets per message matters more
   * than fine-grained load balancing.
   */
  batchSize?: number;
}

function defaultSize(): number {
  const nav = (globalThis as { navigator?: { hardwareConcurrency?: number } }).navigator;
  const n = nav?.hardwareConcurrency;
  return Math.max(1, Math.min(8, typeof n === 'number' && n > 0 ? n : 4));
}

const defaultSpawn: SpawnFn = async (url: URL): Promise<PoolWorker> => {
  const G = globalThis as { Worker?: new (u: URL, o?: { type: string }) => unknown };
  if (typeof G.Worker === 'function') {
    const w = new G.Worker(url, { type: 'module' }) as unknown as {
      postMessage(m: unknown, t?: ArrayBufferLike[]): void;
      addEventListener(t: string, f: (ev: MessageEvent | ErrorEvent) => void): void;
      terminate(): void;
    };
    return {
      post: (m, t) => w.postMessage(m, t),
      onMessage: (fn) =>
        w.addEventListener('message', (ev) => fn((ev as MessageEvent).data as WorkerReply)),
      onError: (fn) =>
        w.addEventListener('error', (ev) =>
          fn(new Error((ev as ErrorEvent).message ?? 'worker error')),
        ),
      terminate: () => w.terminate(),
    };
  }
  // Indirect specifier: keeps the TypeScript build free of a @types/node
  // dependency, and keeps browser bundlers from trying to resolve a node: URL.
  const spec = 'node:worker_threads';
  const wt = (await import(spec)) as {
    Worker: new (u: URL) => {
      postMessage(m: unknown, t?: unknown): void;
      on(ev: string, fn: (arg: never) => void): void;
      terminate(): Promise<number>;
      unref(): void;
    };
  };
  const w = new wt.Worker(url);
  w.unref();
  return {
    post: (m, t) => w.postMessage(m, t as never),
    onMessage: (fn) => w.on('message', (m: WorkerReply) => fn(m)),
    onError: (fn) => w.on('error', fn),
    terminate: () => w.terminate() as unknown as Promise<void>,
  };
};

interface Pending {
  resolve: (r: SimJobResult[]) => void;
  reject: (e: Error) => void;
  worker: number;
}

export class WorkerPool {
  private workers: PoolWorker[] = [];
  private idle: number[] = [];
  private pending = new Map<number, Pending>();
  private queue: { batch: WorkerRequest; resolve: Pending['resolve']; reject: Pending['reject'] }[] =
    [];
  private nextBatch = 1;
  private readyPromise: Promise<void>;
  private readonly batchSize: number;

  constructor(opts: WorkerPoolOptions = {}) {
    const size = opts.size ?? defaultSize();
    this.batchSize = Math.max(1, opts.batchSize ?? 4);
    const url = opts.workerUrl ?? new URL('./worker.js', import.meta.url);
    const spawn = opts.spawn ?? defaultSpawn;
    this.readyPromise = (async () => {
      for (let i = 0; i < size; i++) {
        const w = await spawn(url);
        const index = i;
        w.onMessage((msg) => this.receive(index, msg));
        w.onError((err) => this.fail(index, err));
        this.workers.push(w);
        this.idle.push(index);
      }
    })();
  }

  get size(): number {
    return this.workers.length;
  }

  ready(): Promise<void> {
    return this.readyPromise;
  }

  /**
   * Send a receiver grid to every worker once, under `id`. Jobs then reference
   * it via `receiversRef` instead of carrying 3n doubles apiece.
   *
   * Each worker needs its own copy, so this is a structured clone per worker,
   * not a transfer — but it happens once per show, not once per set.
   */
  async uploadReceivers(id: string, data: Float64Array): Promise<void> {
    await this.readyPromise;
    for (const w of this.workers) w.post({ type: 'receivers', id, data }, []);
  }

  async dropReceivers(id: string): Promise<void> {
    await this.readyPromise;
    for (const w of this.workers) w.post({ type: 'dropReceivers', id }, []);
  }

  /** Run every job, in batches, across the pool. Results come back in job order. */
  async run(jobs: readonly SimJob[]): Promise<SimJobResult[]> {
    await this.readyPromise;
    if (jobs.length === 0) return [];

    const batches: SimJob[][] = [];
    for (let i = 0; i < jobs.length; i += this.batchSize) {
      batches.push(jobs.slice(i, i + this.batchSize) as SimJob[]);
    }

    const settled = await Promise.all(batches.map((b) => this.dispatch(b)));
    const byId = new Map<string | number, SimJobResult>();
    for (const group of settled) for (const r of group) byId.set(r.id, r);
    return jobs.map((j) => {
      const r = byId.get(j.id);
      if (!r) throw new Error(`no result returned for job ${String(j.id)}`);
      return r;
    });
  }

  private dispatch(jobs: SimJob[]): Promise<SimJobResult[]> {
    const batch = this.nextBatch++;
    const transfer: ArrayBufferLike[] = [];
    for (const j of jobs) if (j.receiversFt) transfer.push(j.receiversFt.buffer);
    const request: WorkerRequest = { type: 'simulate', batch, jobs };
    return new Promise<SimJobResult[]>((resolve, reject) => {
      const idle = this.idle.pop();
      if (idle === undefined) {
        this.queue.push({ batch: request, resolve, reject });
        return;
      }
      this.pending.set(batch, { resolve, reject, worker: idle });
      this.workers[idle].post(request, transfer);
    });
  }

  private receive(index: number, msg: WorkerReply): void {
    if (msg.type === 'ack') return;
    const batch = msg.batch;
    if (batch === undefined) return;
    const p = this.pending.get(batch);
    if (!p) return;
    this.pending.delete(batch);
    if (msg.type === 'error') p.reject(new Error(msg.message));
    else p.resolve(msg.results);
    this.release(index);
  }

  private fail(index: number, err: Error): void {
    for (const [batch, p] of this.pending) {
      if (p.worker === index) {
        this.pending.delete(batch);
        p.reject(err);
      }
    }
    this.release(index);
  }

  private release(index: number): void {
    const next = this.queue.shift();
    if (!next) {
      this.idle.push(index);
      return;
    }
    const req = next.batch as { batch: number; jobs: SimJob[] };
    const transfer: ArrayBufferLike[] = [];
    for (const j of req.jobs) if (j.receiversFt) transfer.push(j.receiversFt.buffer);
    this.pending.set(req.batch, { resolve: next.resolve, reject: next.reject, worker: index });
    this.workers[index].post(next.batch, transfer);
  }

  async terminate(): Promise<void> {
    await this.readyPromise;
    await Promise.all(this.workers.map((w) => w.terminate()));
    this.workers = [];
    this.idle = [];
  }
}
