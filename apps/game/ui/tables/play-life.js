/* Life, as play-life plays it (adapters/stdlib/play-life): a square soup,
   --size cells a side (16), each alive at --density percent (35), drawn from
   the seeded stream; run --generations steps (64, at most 500) of a Life-like
   rule (B3/S23) on an unbounded plane. How it ends is found as the add-on
   finds it, by each board's shape hash from its top-left live cell:
   dies, still, oscillator (back in place every P), spaceship (back, moved,
   every P), running (nothing repeated). The same seed and settings make the
   same game here and on the record. You can also draw the first board. */
const MAX_GENERATIONS = 500, MAX_SIZE = 64;
const RULE = /^B([0-8]*)\/S([0-8]*)$/;

function ruleOf(text) {
  const m = RULE.exec(text.trim().toUpperCase());
  if (!m) throw new Error(`${text} isn't a Life-like rule: B3/S23, for instance.`);
  return [new Set([...m[1]].map(Number)), new Set([...m[2]].map(Number))];
}
const key = (x, y) => `${x},${y}`;
function soup(seedText, size, density) {
  const rng = Stream.fromText(seedText), board = new Map();
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (rng.below(100) < density) board.set(key(x, y), [x, y]);
  return board;
}
function step(board, birth, survive) {
  const counts = new Map();
  for (const [x, y] of board.values()) for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) if (dx || dy) {
    const k = key(x + dx, y + dy), c = counts.get(k); counts.set(k, c ? [c[0], c[1], c[2] + 1] : [x + dx, y + dy, 1]);
  }
  const next = new Map();
  for (const [k, [x, y, n]] of counts) if (board.has(k) ? survive.has(n) : birth.has(n)) next.set(k, [x, y]);
  return next;
}
function shape(board) {
  if (!board.size) return [hex(sha256(utf8(""))).slice(0, 16), 0, 0];
  const cells = [...board.values()];
  const x0 = Math.min(...cells.map((c) => c[0])), y0 = Math.min(...cells.map((c) => c[1]));
  const s = cells.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([x, y]) => `${x - x0},${y - y0}`).join(";");
  return [hex(sha256(utf8(s))).slice(0, 16), x0, y0];
}
function runLife(first, generations, ruleText) {
  const [birth, survive] = ruleOf(ruleText);
  const boards = [], steps = [], seen = new Map();
  let board = first, fate = "running", period = 0;
  for (let g = 0; g <= generations; g++) {
    const [h, x, y] = shape(board);
    steps.push([board.size, x, y, h]); boards.push(board);
    if (!board.size) { fate = "dies"; break; }
    if (seen.has(h)) {
      const firstSeen = seen.get(h); period = g - firstSeen;
      const moved = x !== steps[firstSeen][1] || y !== steps[firstSeen][2];
      fate = moved ? "spaceship" : period === 1 ? "still" : "oscillator"; break;
    }
    seen.set(h, g);
    if (g < generations) board = step(board, birth, survive);
  }
  return { boards, steps, fate, period };
}
window.__life = (seedText, size, density, generations, rule) => { const r = runLife(soup(seedText, size, density), generations, rule); return { fate: r.fate, period: r.period, steps: r.steps.length, first: r.steps[0], last: r.steps[r.steps.length - 1] }; };

const FATE = { dies: "It dies out", still: "It settles still", oscillator: "It oscillates", spaceship: "A spaceship: it repeats, moved", running: "Still running: nothing repeated" };

let opts = { seed: seedWords(), size: 16, density: 35, generations: 64, rule: "B3/S23" };
let G = null, gen = 0, timer = null, speed = 6, drawn = null, sheet = [];

function start(fromDrawn) {
  stop();
  try {
    ruleOf(opts.rule);
    if (!(opts.size >= 1 && opts.size <= MAX_SIZE)) throw new Error(`a soup is 1 to ${MAX_SIZE} cells a side.`);
    if (!(opts.density >= 0 && opts.density <= 100)) throw new Error("density is a percentage, 0 to 100.");
    if (!(opts.generations >= 0 && opts.generations <= MAX_GENERATIONS)) throw new Error(`at most ${MAX_GENERATIONS} generations.`);
    const first = fromDrawn ? new Map(drawn) : soup(opts.seed, opts.size, opts.density);
    G = { ...runLife(first, opts.generations, opts.rule), by: fromDrawn ? "drawn" : opts.seed, logged: false };
  } catch (e) { return frame.refuse(e.message); }
  if (!fromDrawn) drawn = null;
  gen = 0; render(); play();
}
function play() { stop(); if (gen >= G.boards.length - 1) gen = 0; timer = setInterval(() => { if (gen < G.boards.length - 1) { gen++; render(); } else { stop(); finish(); render(); } }, Math.round(1000 / speed)); render(); }
function stop() { if (timer) { clearInterval(timer); timer = null; } }
function finish() {
  if (G.logged) return; G.logged = true;
  const f = G.fate + (G.period ? ` ·${G.period}` : "");
  sheet.unshift({ label: String(sheet.length + 1), cells: [esc(G.by), esc(f), String(G.steps.length - 1)] });
  frame.log(`<b>${esc(G.by)}</b>: ${esc(FATE[G.fate])}${G.period ? ` (period ${G.period})` : ""} at generation ${G.steps.length - 1}.`);
}

function view() {
  // fit every generation, a cell of margin round it; past 120 a side, follow the current board
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const b of G.boards) for (const [x, y] of b.values()) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  if (x0 === Infinity) return { x0: 0, y0: 0, w: opts.size, h: opts.size };
  if (x1 - x0 > 118 || y1 - y0 > 118) {
    const cur = [...G.boards[gen].values()]; const cx = cur.length ? cur.reduce((a, c) => a + c[0], 0) / cur.length : 0, cy = cur.length ? cur.reduce((a, c) => a + c[1], 0) / cur.length : 0;
    return { x0: Math.round(cx - 60), y0: Math.round(cy - 60), w: 120, h: 120 };
  }
  return { x0: x0 - 1, y0: y0 - 1, w: x1 - x0 + 3, h: y1 - y0 + 3 };
}

function render() {
  const v = G ? view() : { x0: 0, y0: 0, w: opts.size, h: opts.size };
  const px = Math.max(3, Math.min(22, Math.floor(560 / Math.max(v.w, v.h))));
  // the settings and the speed draw once, so typing and dragging survive the animation;
  // only the board and its buttons redraw each generation
  if (!$("lifeform")) frame.stage(`
    <form id="lifeform" class="actions" style="gap:8px" autocomplete="off">
      <label class="count" for="seed">Seed</label><input id="seed" value="${esc(opts.seed)}" spellcheck="false" style="font:inherit;font-family:var(--mono);width:13ch;padding:7px 9px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <label class="count" for="size">Size</label><input id="size" type="number" min="1" max="${MAX_SIZE}" value="${opts.size}" style="font:inherit;width:6ch;padding:7px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <label class="count" for="density">Alive %</label><input id="density" type="number" min="0" max="100" value="${opts.density}" style="font:inherit;width:6ch;padding:7px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <label class="count" for="gens">Steps</label><input id="gens" type="number" min="0" max="${MAX_GENERATIONS}" value="${opts.generations}" style="font:inherit;width:7.5ch;padding:7px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <label class="count" for="rule">Rule</label><input id="rule" value="${esc(opts.rule)}" spellcheck="false" style="font:inherit;font-family:var(--mono);width:9ch;padding:7px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <button class="btn" type="submit">Seed the soup</button>
      <button class="btn ghost" type="button" data-do="fresh">New seed</button>
    </form>
    <div id="lifeview"></div>
    <div id="lifectl"></div>
    <div class="actions" style="gap:8px"><label class="count" for="speed">Speed</label><input id="speed" type="range" min="1" max="30" value="${speed}"></div>`);
  $("lifeview").innerHTML = `<canvas id="life" width="${v.w * px}" height="${v.h * px}" style="max-width:100%;background:#06100a;border-radius:8px;box-shadow:0 10px 24px -12px #000;cursor:${timer ? "default" : "crosshair"};image-rendering:pixelated" role="img" aria-label="Generation ${gen}, ${G ? G.boards[gen].size : 0} cells alive"></canvas>`;
  $("lifectl").innerHTML = `<div class="actions" style="gap:8px">
      <button class="btn ghost" data-do="back" aria-label="Back one generation">◂</button>
      <button class="btn" data-do="${timer ? "pause" : "play"}">${timer ? "Pause" : gen >= (G ? G.boards.length - 1 : 0) ? "Play again" : "Play"}</button>
      <button class="btn ghost" data-do="step" aria-label="Forward one generation">▸</button>
      <button class="btn ghost" data-do="draw">Draw your own</button>
    </div>`;
  const cv = $("life"), cx = cv.getContext("2d");
  if (G) {
    cx.fillStyle = "#9ff0b4";
    for (const [x, y] of G.boards[gen].values()) { const sx = x - v.x0, sy = y - v.y0; if (sx >= 0 && sy >= 0 && sx < v.w && sy < v.h) cx.fillRect(sx * px + 0.5, sy * px + 0.5, px - 1, px - 1); }
  }
  cv.addEventListener("click", (e) => {
    if (timer || !G) return;
    const r = cv.getBoundingClientRect(), x = Math.floor(((e.clientX - r.left) / r.width) * v.w) + v.x0, y = Math.floor(((e.clientY - r.top) / r.height) * v.h) + v.y0;
    drawn = new Map(G.boards[gen]); const k = key(x, y); drawn.has(k) ? drawn.delete(k) : drawn.set(k, [x, y]);
    G = { ...runLife(drawn, opts.generations, opts.rule), by: "drawn", logged: false }; gen = 0; render();
  });
  const ended = G && gen === G.boards.length - 1;
  frame.status(!G ? "" : timer ? `Generation ${gen}` : ended ? `<b>${esc(FATE[G.fate])}</b>${G.period ? `, every ${G.period} generation${G.period > 1 ? "s" : ""}` : ""}, at generation ${gen}.` : `Generation ${gen}. ${gen === 0 ? "Tap cells to change the first board, then play." : ""}`);
  frame.actions("");
  frame.score({ you: -1, head: "Game", cols: ["Seed", "Ended", "Steps"], rows: sheet.slice(0, 20), note: "Kept only while this page is open.", empty: "Each game's ending goes here." });
  frame.deck(G ? [["Generation", `${gen} of ${G.steps.length - 1}`], ["Alive", G.boards[gen].size], ["Rule", opts.rule], ["First board", G.by === "drawn" ? "drawn by you" : `${opts.size}×${opts.size} at ${opts.density}%`]] : [["Generation", "–"]],
    G && G.by !== "drawn" ? `The same game on the record: play.py play-life --table DIR play --seed "${opts.seed}" --size ${opts.size} --density ${opts.density} --generations ${opts.generations} --rule ${opts.rule}` : "A board you draw has no seed: the record plays only seeded soups.");
}

function readForm() { opts = { seed: $("seed").value.trim() || seedWords(), size: +$("size").value, density: +$("density").value, generations: +$("gens").value, rule: $("rule").value.trim().toUpperCase() || "B3/S23" }; }
document.addEventListener("submit", (e) => { if (e.target.id !== "lifeform") return; e.preventDefault(); readForm(); start(false); });
document.addEventListener("input", (e) => { if (e.target.id === "speed") { speed = +e.target.value; if (timer) play(); } });
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-do]"); if (!b) return;
  const d = b.dataset.do;
  if (d === "fresh") { opts.seed = seedWords(); start(false); }
  else if (d === "play") play();
  else if (d === "pause") { stop(); render(); }
  else if (d === "step" && G) { stop(); if (gen < G.boards.length - 1) gen++; if (gen === G.boards.length - 1) finish(); render(); }
  else if (d === "back" && G) { stop(); if (gen > 0) gen--; render(); }
  else if (d === "draw") { stop(); readForm(); drawn = new Map(); G = { ...runLife(drawn, opts.generations, opts.rule), by: "drawn", logged: false }; gen = 0; render(); frame.status("<b>An empty board.</b> Tap cells to bring them alive, then play."); }
});

frame.setup({ seats: false, score: true, deck: true, hints: false, scoreTitle: "Games", deckTitle: "This world", redraw: render });
frame.clearLog();
start(false);
