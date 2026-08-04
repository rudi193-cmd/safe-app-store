/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The capability seam. It is empty, and that is the point.
 *
 * BUILD_PLAN P4 reads "Shell and the first capability · blocked on the core
 * job", and says plainly that "what goes inside it is the one open question".
 * The chassis is settled; the contents are not. So this registry ships with
 * nothing registered, and `capabilities.test.mjs` asserts that it is empty —
 * a gate that fails the moment somebody answers the open question in code
 * instead of with the human who owns it.
 *
 * When the core job is decided, a capability registers itself here and that
 * test changes in the same commit that adds the first one. Until then the shell
 * renders its own chrome, reports its own storage, and offers nothing.
 */

/** @typedef {{id: string, title: string, mount: (root: HTMLElement) => void}} Capability */

/** @type {Map<string, Capability>} */
const registry = new Map();

export function register(capability) {
  for (const field of ['id', 'title', 'mount']) {
    if (!capability?.[field]) throw new Error(`capability is missing ${field}`);
  }
  if (registry.has(capability.id)) throw new Error(`capability ${capability.id} is already registered`);
  registry.set(capability.id, Object.freeze({ ...capability }));
  return capability.id;
}

export const capabilities = () => [...registry.values()];

/**
 * What the shell shows when nothing is registered. Not a placeholder screen
 * pretending a feature is coming — a statement of where the build actually is,
 * which is the same thing the plan says.
 */
export const EMPTY_STATE = Object.freeze({
  title: 'No capability yet',
  body:
    'This is the chassis: shell, storage seam, offline. What goes inside it is ' +
    'the one open question in P4 of the build plan, and it is not an ' +
    'engineering call. Nothing is registered here on purpose.',
});
