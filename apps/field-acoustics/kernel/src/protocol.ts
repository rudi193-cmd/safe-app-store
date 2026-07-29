/**
 * The job/result protocol shared by the worker and the pool.
 *
 * Design constraints, straight out of the browser spike:
 *
 *  - **No SharedArrayBuffer.** COOP/COEP is not available on a plain static
 *    host and turned out not to be needed: this is an embarrassingly parallel
 *    reduction with no cross-worker data dependencies, so each worker owns a
 *    slice of the work, computes into private `Float64Array`s and hands the
 *    buffers back as *transferables*. Zero copies, zero headers.
 *  - **Batch several sets per dispatch.** The spike measured `postMessage`
 *    overhead as significant against a ~25 ms task (4 workers gave ~2x, not 4x).
 *    So the unit of dispatch is a *batch* of jobs, not a job.
 *  - **Upload the receiver grid once.** A whole show re-uses the same seat grid
 *    for every set. Sending 1640x3 doubles per set is pure waste, so receivers
 *    can be uploaded once under an id and referenced afterwards.
 */

import type { Conditions, Performer, SimResult } from './engine.js';
import type { Stadium } from './field.js';

/** Kernel tuning that is safe to send across a worker boundary. */
export interface WireKernelOptions {
  cosTableSize?: number;
  absorptionTableSize?: number;
  tablePrecision?: 'f64' | 'f32';
}

export type OutputName =
  | 'bandSpl'
  | 'directSpl'
  | 'reflectedSpl'
  | 'arrivalMeanMs'
  | 'arrivalSpreadMs'
  | 'dba'
  | 'brightness'
  | 'reflectedRatioDb';

export const ALL_OUTPUTS: readonly OutputName[] = [
  'bandSpl',
  'directSpl',
  'reflectedSpl',
  'arrivalMeanMs',
  'arrivalSpreadMs',
];

export interface SimJob {
  /** Caller-chosen identity, echoed back on the result. */
  id: string | number;
  performers: Performer[];
  /** Flat (n*3) feet. Provide this or `receiversRef`, not both. */
  receiversFt?: Float64Array;
  /** Id of a receiver grid previously uploaded with `UploadReceivers`. */
  receiversRef?: string;
  stadium?: Partial<Stadium>;
  conditions?: Partial<Conditions>;
  options?: WireKernelOptions;
  /** Which arrays to send back. Defaults to `ALL_OUTPUTS`. */
  outputs?: readonly OutputName[];
}

export interface SimJobResult {
  id: string | number;
  nReceivers: number;
  nBands: number;
  /** Only the arrays named in `SimJob.outputs` are present. */
  data: Partial<Record<OutputName, Float64Array>>;
  /** Wall time spent inside `simulate()` for this job, ms. */
  elapsedMs: number;
}

export interface UploadReceivers {
  type: 'receivers';
  id: string;
  data: Float64Array;
}

export interface DropReceivers {
  type: 'dropReceivers';
  id: string;
}

export interface SimulateRequest {
  type: 'simulate';
  /** Correlates the reply with the dispatch; distinct from per-job ids. */
  batch: number;
  jobs: SimJob[];
}

export interface PingRequest {
  type: 'ping';
  batch: number;
}

export type WorkerRequest = SimulateRequest | UploadReceivers | DropReceivers | PingRequest;

export interface SimulateReply {
  type: 'result';
  batch: number;
  results: SimJobResult[];
  /** Wall time for the whole batch inside the worker, ms. */
  elapsedMs: number;
}

export interface AckReply {
  type: 'ack';
  batch?: number;
  id?: string;
}

export interface ErrorReply {
  type: 'error';
  batch?: number;
  id?: string | number;
  message: string;
  stack?: string;
}

export type WorkerReply = SimulateReply | AckReply | ErrorReply;

/** Pull the requested arrays out of a `SimResult`, computing derived ones. */
export function selectOutputs(
  res: SimResult,
  outputs: readonly OutputName[],
  derive: {
    dba: (r: SimResult) => Float64Array;
    brightness: (r: SimResult) => Float64Array;
    reflectedRatioDb: (r: SimResult) => Float64Array;
  },
): { data: Partial<Record<OutputName, Float64Array>>; transfer: ArrayBufferLike[] } {
  const data: Partial<Record<OutputName, Float64Array>> = {};
  const transfer: ArrayBufferLike[] = [];
  for (const name of outputs) {
    let arr: Float64Array;
    switch (name) {
      case 'bandSpl':
        arr = res.bandSpl;
        break;
      case 'directSpl':
        arr = res.directSpl;
        break;
      case 'reflectedSpl':
        arr = res.reflectedSpl;
        break;
      case 'arrivalMeanMs':
        arr = res.arrivalMeanMs;
        break;
      case 'arrivalSpreadMs':
        arr = res.arrivalSpreadMs;
        break;
      case 'dba':
        arr = derive.dba(res);
        break;
      case 'brightness':
        arr = derive.brightness(res);
        break;
      case 'reflectedRatioDb':
        arr = derive.reflectedRatioDb(res);
        break;
      default:
        throw new RangeError(`unknown output ${JSON.stringify(name)}`);
    }
    data[name] = arr;
    transfer.push(arr.buffer);
  }
  return { data, transfer };
}
