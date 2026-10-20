/* Replays jobs through the browser engine and prints what it made.
 * Driven by tests/test_differential.py; reads JSON on stdin:
 *   {"boards": [{seed, n, k}], "games": [{seed, n, k, bank, words, moves}],
 *    "daily": [{day, randomness}]}
 * and writes {"boards": [{regions, solution} | {error}], "games": [[step...]],
 * "daily": [{round, seed}]},
 * each step {said, state} or {refused: true, state}. */
"use strict";
const path = require("path");
const eng = require(path.join(__dirname, "..", "catgrid", "web", "engine.js"));

function board(job) {
  try {
    const b = eng.generate(job.seed, job.n, job.k);
    return { regions: b.regions, solution: b.solution };
  } catch (e) {
    if (e instanceof eng.NoBoard) return { error: "NoBoard" };
    throw e;
  }
}

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  const jobs = JSON.parse(raw);
  const out = { boards: (jobs.boards || []).map(board), games: [] };
  const crypto = require("crypto");
  out.daily = (jobs.daily || []).map((j) => ({
    round: eng.roundFor(j.day),
    seed: eng.seedFromDigest(crypto.createHash("sha256").update(Buffer.from(j.randomness, "hex")).digest()),
  }));
  for (const job of jobs.games || []) {
    const g = new eng.Game(eng.generate(job.seed, job.n, job.k), job.seed,
      { bank: job.bank, words: job.words });
    const trace = [];
    for (const move of job.moves) {
      try {
        const said = g.step(move);
        trace.push({ said: said, state: g.state() });
      } catch (e) {
        if (!(e instanceof eng.Refused)) throw e;
        trace.push({ refused: true, state: g.state() });
      }
    }
    out.games.push(trace);
  }
  process.stdout.write(JSON.stringify(out));
});
