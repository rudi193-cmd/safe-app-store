/**
 * Cross-persona integration stub.
 *
 * Gerald currently runs standalone on Devvit Redis. The authoring system that
 * holds Gerald's canon also holds canon for other personas (Professor
 * Oakenscroll, etc.). When those personas come online, this module is the
 * single seam where Gerald learns about them.
 *
 * Expected shape when implemented:
 *
 *   - readSharedState(context, key): read a value from a shared store that
 *     other personas can also read/write. Probably an HTTP call to a backend
 *     service — which means devvit.json's `http.enable` must be flipped to
 *     true and the backend domain added to `http.domains`.
 *
 *   - writeWitnessedEvent(context, event): append a witnessing event to a
 *     shared log so other personas can observe what Gerald has seen.
 *
 *   - shouldDeferTo(personaName, context): ask whether another persona has
 *     already handled a given event, so Gerald stays silent when a sibling
 *     has spoken.
 *
 * DO NOT implement any of this until the authoring system has a real API.
 * Premature implementation will get retrofitted to nothing.
 */

export const CROSS_PERSONA_ENABLED = false;
