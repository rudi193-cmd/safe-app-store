/* Replays move scripts through the browser engine and prints the state trace.
 * Driven by tests/test_differential.py; reads {seed, moves} JSON on stdin. */
"use strict";
const path = require("path");
const fs = require("fs");
const eng = require(path.join(__dirname, "..", "bureau", "web", "engine.js"));
eng.setData(JSON.parse(fs.readFileSync(path.join(__dirname, "..", "bureau", "web", "data.json"), "utf8")));
const Session = eng.Session;

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  const out = [];
  for (const job of JSON.parse(raw)) {
    const s = new Session(job.seed);
    const trace = [];
    for (const [verb, arg] of job.moves) {
      if (verb === "go") s.visit(arg);
      else s.hand(arg);
      trace.push(s.state());
    }
    out.push({ seed: job.seed, trace: trace });
  }
  process.stdout.write(JSON.stringify(out));
});
