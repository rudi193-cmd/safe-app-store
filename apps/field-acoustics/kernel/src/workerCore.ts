/**
 * The worker's message handler, factored out of `worker.ts` so it can be
 * exercised synchronously by the tests without spawning a thread.
 */

import { brightness, dba, makeConditions, reflectedRatioDb, simulate } from './engine.js';
import { makeStadium } from './field.js';
import {
  ALL_OUTPUTS,
  type SimJobResult,
  type WorkerReply,
  type WorkerRequest,
  selectOutputs,
} from './protocol.js';

const derive = { dba, brightness, reflectedRatioDb };

export class WorkerCore {
  private receivers = new Map<string, Float64Array>();

  handle(msg: WorkerRequest): { reply: WorkerReply; transfer: ArrayBufferLike[] } {
    switch (msg.type) {
      case 'receivers':
        this.receivers.set(msg.id, msg.data);
        return { reply: { type: 'ack', id: msg.id }, transfer: [] };

      case 'dropReceivers':
        this.receivers.delete(msg.id);
        return { reply: { type: 'ack', id: msg.id }, transfer: [] };

      case 'ping':
        return { reply: { type: 'ack', batch: msg.batch }, transfer: [] };

      case 'simulate': {
        const started = now();
        const results: SimJobResult[] = [];
        const transfer: ArrayBufferLike[] = [];
        for (const job of msg.jobs) {
          let rcv = job.receiversFt;
          if (!rcv && job.receiversRef !== undefined) {
            rcv = this.receivers.get(job.receiversRef);
            if (!rcv) {
              return {
                reply: {
                  type: 'error',
                  batch: msg.batch,
                  id: job.id,
                  message: `no receiver grid uploaded under id ${JSON.stringify(job.receiversRef)}`,
                },
                transfer: [],
              };
            }
          }
          if (!rcv) {
            return {
              reply: {
                type: 'error',
                batch: msg.batch,
                id: job.id,
                message: 'job has neither receiversFt nor receiversRef',
              },
              transfer: [],
            };
          }
          const t0 = now();
          const res = simulate(
            job.performers,
            rcv,
            makeStadium(job.stadium ?? {}),
            makeConditions(job.conditions ?? {}),
            job.options ?? {},
          );
          const elapsedMs = now() - t0;
          const sel = selectOutputs(res, job.outputs ?? ALL_OUTPUTS, derive);
          results.push({
            id: job.id,
            nReceivers: res.nReceivers,
            nBands: res.nBands,
            data: sel.data,
            elapsedMs,
          });
          transfer.push(...sel.transfer);
        }
        return {
          reply: { type: 'result', batch: msg.batch, results, elapsedMs: now() - started },
          transfer,
        };
      }

      default:
        return {
          reply: {
            type: 'error',
            message: `unknown request type ${JSON.stringify((msg as { type: string }).type)}`,
          },
          transfer: [],
        };
    }
  }
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}
