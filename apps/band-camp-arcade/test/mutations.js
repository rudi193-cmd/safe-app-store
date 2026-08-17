// Six mutations, one per game — each breaks the exact mechanism its
// corresponding suite checks, and nothing else. "A gate that cannot fail is
// not a gate": these are what let test/run.js --mutations prove the six
// suites actually catch a real regression instead of passing vacuously.
//
// `expect` names the suite gate(s) that must go red when this mutation is
// applied. `file` is the path (relative to the app root) the mutation server
// rewrites on the way out.

export const MUTATIONS = [
  {
    name: 'tuning: best time never saves',
    file: 'games/tuning-note-purgatory/index.html',
    find: 'if (ms > best) {',
    replace: 'if (false) {',
    expect: ['personal best updates after a run'],
    describe: 'saveBestIfBetter never fires, so the best-time gate should catch a run that never improves',
  },
  {
    name: 'pit-crew: clearing a level no longer scores',
    file: 'games/pit-crew-simulator/index.html',
    find: 'score += 100 * instruments.length;',
    replace: 'score += 0;',
    expect: ['clearing a level increases the score'],
    describe: 'a perfectly placed instrument should still raise the score; this mutation keeps it at zero',
  },
  {
    name: 'sweat-tracker: worst/best day swapped',
    file: 'games/uniform-sweat-tracker/index.html',
    find: 'const sorted = [...entries].sort((a, b) => b.score - a.score || b.createdAt - a.createdAt);',
    replace: 'const sorted = [...entries].sort((a, b) => a.score - b.score || b.createdAt - a.createdAt);',
    expect: ['worst day shows the highest-suffering entry', 'best day shows the lowest-suffering entry'],
    describe: 'reverses the sort, so both ends flip: "worst day" shows the mildest entry and "best day" shows the harshest',
  },
  {
    name: 'bingo: BINGO can never trigger',
    file: 'games/sectional-bingo/index.html',
    find: 'return lines.some(line => line.every(i => marked[i]));',
    replace: 'return false;',
    expect: ['marking a full row triggers BINGO'],
    describe: 'checkBingo always reports no line complete, even with a full row marked',
  },
  {
    name: 'ge-score-roast: brutal band misclassified',
    file: 'games/ge-score-roast/index.html',
    find: '{ key: "brutal", name: "Brutal", color: "var(--brutal)", max: 40 },',
    replace: '{ key: "brutal", name: "Brutal", color: "var(--brutal)", max: 0 },',
    expect: ['a low score classifies as Brutal'],
    describe: 'shrinks the brutal band to nothing, so a score of 22 falls through to Backhanded instead',
  },
  {
    name: 'drum-major: the sequence never grows',
    file: 'games/drum-major-says/index.html',
    find: 'sequence.push(randomCommand()); // extend for the next round',
    replace: '/* the drum major stops adding calls */;',
    expect: ['a full correct repeat grows the sequence to the next round'],
    describe: 'a cleared round should add one more call; this keeps the sequence frozen at length 1 forever',
  },
];
