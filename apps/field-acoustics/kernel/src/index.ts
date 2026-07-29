/**
 * A field-acoustics kernel for marching-arts drill design — TypeScript port of
 * the `dcisim` propagation core.
 *
 * Answers one question quantitatively: what changes in the audience when an
 * ensemble stops facing the front sideline and turns in to face the middle of
 * the field?
 *
 * Provenance: the underlying model's own verdict on itself is ASSUMED. Its
 * instrument power spectra are representative rather than measured and its rear
 * directivity is carried to an asserted front-to-back ratio. This port is
 * faithful to it, limitations included; see README.md.
 */

export { A_WEIGHT, BANDS, N_BANDS, absorptionCoefficients, speedOfSound } from './atmosphere.js';
export { besselJ1, pistonFactor } from './bessel.js';
export {
  DEFAULT_FRONT_TO_BACK,
  DEFAULT_SIDELOBE_FLOOR,
  Directivity,
  REFERENCE_DI,
  THETA_GRID,
  buildCosTable,
  buildDirectivityTable,
  effectiveRadius,
} from './directivity.js';
export type { CosDirectivityTable } from './directivity.js';
export {
  DEFAULT_CONDITIONS,
  HF_BANDS,
  LF_BANDS,
  MIN_RANGE_M,
  SILENT_DB,
  brightness,
  dba,
  makeConditions,
  reflectedRatioDb,
  simulate,
} from './engine.js';
export type { Conditions, KernelOptions, Performer, SimResult } from './engine.js';
export {
  DEFAULT_STADIUM,
  FIELD_CENTER,
  FT_PER_M,
  STEP_FT,
  farSidePlaneYFt,
  makeStadium,
  namedSeats,
  seatGrid,
  stepsFromSideline,
  yardsToX,
} from './field.js';
export type { SeatGrid, Stadium } from './field.js';
export { CATALOG, Instrument } from './instruments.js';
export { FORMS, applyFacing, arcForm, blockForm } from './drill.js';
export type { FacingMode } from './drill.js';
export { ALL_OUTPUTS } from './protocol.js';
export type {
  OutputName,
  SimJob,
  SimJobResult,
  WireKernelOptions,
  WorkerReply,
  WorkerRequest,
} from './protocol.js';
export { WorkerPool } from './pool.js';
export type { PoolWorker, SpawnFn, WorkerPoolOptions } from './pool.js';
export { WorkerCore } from './workerCore.js';
