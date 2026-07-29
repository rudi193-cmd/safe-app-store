/**
 * Silence the SQLite-WASM library's own stderr logging during tests.
 *
 * Several tests deliberately provoke `SQLITE_CONSTRAINT_CHECK` — a blank
 * `source`, a sealed grant with no signer, a band outside the range. Those are
 * successes, and the library prints each one to `console.error` before throwing.
 * Left alone, the useful output of a passing run is buried under expected
 * failures, and a reader stops looking at stderr, which is where the *un*expected
 * failure would appear.
 *
 * Nothing is lost: every one of those errors is also thrown, and every test that
 * expects one asserts on the throw. This suppresses the duplicate narration, not
 * the signal.
 */

export function quiet(api) {
  if (!api?.config) return () => {};
  const saved = { error: api.config.error, warn: api.config.warn };
  api.config.error = () => {};
  api.config.warn = () => {};
  return () => {
    api.config.error = saved.error;
    api.config.warn = saved.warn;
  };
}
