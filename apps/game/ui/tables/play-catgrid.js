/* Catgrid, as play-catgrid builds and plays it (adapters/stdlib/play-catgrid):
   an N x N board (4 to 8) cut into N connected colour regions; the answer puts
   one cat in every row, column and region, no two touching even at a corner,
   and the board is built so that answer is the only one. A cat on the answer
   stays; a cat off it costs one of three hearts and isn't placed. The board is
   built from the seeded stream exactly as the add-on builds it, so the same
   seed and size give the same board here and on the record. */
const MIN_SIZE = 4, MAX_SIZE = 8, HEARTS = 3, DRAWS = 300, REPAIRS = 200;
const REGION_TINT = ["#f6c1cc", "#bcdcf5", "#c8ecc0", "#ffe3a8", "#ddd0f7", "#f9cfae", "#b9ece6", "#e8e2d2"];

function* solutions(n, region) {
  const cols = [];
  function* go(row) {
    if (row === n) { yield cols.slice(); return; }
    for (let c = 0; c < n; c++) {
      if (cols.includes(c) || (cols.length && Math.abs(c - cols[cols.length - 1]) < 2)) continue;
      let clash = false;
      for (let r = 0; r < row; r++) if (region[r * n + cols[r]] === region[row * n + c]) { clash = true; break; }
      if (clash) continue;
      cols.push(c); yield* go(row + 1); cols.pop();
    }
  }
  yield* go(0);
}
function placement(n, rng) {
  const cols = [];
  const go = (row) => {
    if (row === n) return true;
    for (const c of rng.shuffled([...Array(n).keys()])) {
      if (!cols.includes(c) && (!cols.length || Math.abs(c - cols[cols.length - 1]) >= 2)) {
        cols.push(c); if (go(row + 1)) return true; cols.pop();
      }
    }
    return false;
  };
  go(0);
  return cols;
}
function neighbours(i, n) {
  const r = Math.floor(i / n), c = i % n;
  return [[r - 1, c], [r + 1, c], [r, c - 1], [r, c + 1]].filter(([rr, cc]) => rr >= 0 && rr < n && cc >= 0 && cc < n).map(([rr, cc]) => rr * n + cc);
}
function grow(n, cols, rng) {
  const region = new Array(n * n).fill(0);
  cols.forEach((c, r) => { region[r * n + c] = r + 1; });
  for (let k = 0; k < n * n - n; k++) {
    const frontier = new Map();
    region.forEach((owner, i) => { if (owner) for (const j of neighbours(i, n)) if (!region[j]) { if (!frontier.has(owner)) frontier.set(owner, new Set()); frontier.get(owner).add(j); } });
    const owner = rng.pick([...frontier.keys()].sort((a, b) => a - b));
    region[rng.pick([...frontier.get(owner)].sort((a, b) => a - b))] = owner;
  }
  return region;
}
function connected(region, n, owner) {
  const cells = region.map((o, i) => (o === owner ? i : -1)).filter((i) => i >= 0);
  const seen = new Set([cells[0]]), todo = [cells[0]];
  while (todo.length) for (const j of neighbours(todo.pop(), n)) if (region[j] === owner && !seen.has(j)) { seen.add(j); todo.push(j); }
  return seen.size === cells.length;
}
function repair(n, cols, region, rng) {
  const cats = new Set(cols.map((c, r) => r * n + c));
  for (let k = 0; k < REPAIRS; k++) {
    let other = null;
    for (const s of solutions(n, region)) if (s.some((c, i) => c !== cols[i])) { other = s; break; }
    if (!other) return true;
    const set = new Map();
    other.forEach((c, r) => { const i = r * n + c; if (cats.has(i)) return; for (const j of neighbours(i, n)) if (region[j] !== region[i]) set.set(`${i},${region[j]}`, [i, region[j]]); });
    const moves = [...set.values()].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let moved = false;
    for (const [i, to] of rng.shuffled(moves)) {
      const was = region[i]; region[i] = to;
      if (connected(region, n, was)) { moved = true; break; }
      region[i] = was;
    }
    if (!moved) return false;
  }
  return false;
}
function canonical(region) { const seen = new Map(); return region.map((o) => { if (!seen.has(o)) seen.set(o, seen.size + 1); return seen.get(o); }); }
function buildBoard(seedText, n) {
  const rng = Stream.fromText(seedText);
  for (let d = 0; d < DRAWS; d++) {
    const cols = placement(n, rng), region = grow(n, cols, rng);
    if (repair(n, cols, region, rng)) return { regions: canonical(region), answer: cols };
  }
  throw new Error(`no ${n}x${n} board with one answer in ${DRAWS} draws`);
}
window.__catgrid = buildBoard; // for checking against the add-on

const address = (r, c) => `${String.fromCharCode(65 + r)}${c + 1}`;

let size = 5, seed = seedWords(), B = null, played = [], sheet = [];

function newBoard(text, n) {
  seed = text; size = n;
  try { B = { ...buildBoard(seed, size), cats: new Set(), misses: new Set(), hearts: HEARTS, moves: [], over: null }; }
  catch (e) { return frame.refuse(e.message); }
  frame.log(`A ${size}×${size} board, seed “${esc(seed)}”.`);
  render();
}
function place(r, c) {
  if (B.over) return;
  const i = r * size + c;
  if (B.cats.has(i)) return;
  B.moves.push(address(r, c));
  if (B.answer[r] === c) { B.cats.add(i); frame.log(`${address(r, c)}: a cat.`); }
  else { B.hearts--; B.misses.add(i); frame.log(`${address(r, c)}: not there. ${B.hearts} heart${B.hearts === 1 ? "" : "s"} left.`); }
  if (B.cats.size === size) end("won");
  else if (!B.hearts) end("lost");
  render();
}
function end(how) {
  B.over = how;
  sheet.unshift({ label: String(sheet.length + 1), cells: [esc(seed), `${size}×${size}`, how === "won" ? `won · ${"♥".repeat(B.hearts)}` : "lost"] });
  frame.log(`<b>${how === "won" ? "Solved." : "Out of hearts."}</b> Moves: ${B.moves.join(",")}`);
}

function ruledOut(i) {
  const r = Math.floor(i / size), c = i % size;
  for (const k of B.cats) {
    const kr = Math.floor(k / size), kc = k % size;
    if (kr === r || kc === c || B.regions[k] === B.regions[i] || (Math.abs(kr - r) <= 1 && Math.abs(kc - c) <= 1)) return true;
  }
  return false;
}

function render() {
  const cell = Math.min(64, Math.floor(520 / size));
  let grid = "";
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) {
    const i = r * size + c, reg = B.regions[i];
    const edge = (rr, cc) => rr < 0 || cc < 0 || rr >= size || cc >= size || B.regions[rr * size + cc] !== reg;
    const bw = (e) => (e ? "3px solid #2a1f22" : "1px solid #2a1f2233");
    const cat = B.cats.has(i), miss = B.misses.has(i);
    const show = B.over === "lost" && B.answer[r] === c && !cat;
    const dim = frame.hints && !cat && !B.over && ruledOut(i);
    grid += `<button data-cell="${r},${c}" aria-label="${address(r, c)}${cat ? ", a cat" : miss ? ", not there" : ""}" ${B.over || cat ? "disabled" : ""}
      style="width:${cell}px;height:${cell}px;background:${REGION_TINT[(reg - 1) % 8]};border-top:${bw(edge(r - 1, c))};border-bottom:${bw(edge(r + 1, c))};border-left:${bw(edge(r, c - 1))};border-right:${bw(edge(r, c + 1))};display:grid;place-items:center;font-size:${cell * 0.55}px;line-height:1;${dim ? "filter:brightness(.62)" : ""}">${cat ? "🐈" : miss ? `<span style="color:#b3261e;font-weight:800;font-size:${cell * 0.4}px">×</span>` : show ? `<span style="opacity:.45">🐈</span>` : ""}</button>`;
  }
  const labels = (n, f) => [...Array(n).keys()].map(f).join("");
  frame.stage(`
    <form id="seedform" class="actions" style="gap:8px" autocomplete="off">
      <label class="count" for="seed">Seed</label>
      <input id="seed" value="${esc(seed)}" spellcheck="false" style="font:inherit;font-family:var(--mono);width:14ch;padding:7px 10px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <label class="count" for="size">Size</label>
      <select id="size" style="font:inherit;padding:7px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">${[4, 5, 6, 7, 8].map((n) => `<option ${n === size ? "selected" : ""}>${n}</option>`).join("")}</select>
      <button class="btn" type="submit">Build this board</button>
      <button class="btn ghost" type="button" data-do="fresh">A new seed</button>
    </form>
    <div style="display:grid;grid-template-columns:auto auto;gap:4px;justify-content:center;align-items:end">
      <span></span><div style="display:grid;grid-template-columns:repeat(${size},${cell}px)">${labels(size, (c) => `<span class="count">${c + 1}</span>`)}</div>
      <div style="display:grid;grid-template-rows:repeat(${size},${cell}px);align-items:center">${labels(size, (r) => `<span class="count">${String.fromCharCode(65 + r)}</span>`)}</div>
      <div style="display:grid;grid-template-columns:repeat(${size},${cell}px);border:3px solid #2a1f22;border-radius:6px;overflow:hidden;box-shadow:0 10px 24px -12px #000">${grid}</div>
    </div>`);
  frame.status(B.over === "won" ? "<b>Solved.</b> Every row, column and colour has its cat." : B.over === "lost" ? "<b>Out of hearts.</b> The faint cats were the answer." : `<b>${"♥".repeat(B.hearts)}${"♡".repeat(HEARTS - B.hearts)}</b> One cat in every row, column and colour; no two touching, even at a corner.`);
  frame.actions(B.over ? `<button class="btn" data-do="fresh">Another board</button>` : "");
  frame.score({ you: -1, head: "Board", cols: ["Seed", "Size", "How it went"], rows: sheet.slice(0, 20), note: "Kept only while this page is open.", empty: "Your boards go here." });
  frame.deck([["Size", `${size}×${size}`], ["Cats placed", `${B.cats.size} of ${size}`], ["Hearts", `${B.hearts} of ${HEARTS}`], ["Answers", "exactly one"]],
    `The same seed and size build this board on the record too: play.py play-catgrid --table DIR play --seed "${seed}" --size ${size}`);
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.disabled) return;
  if (b.dataset.cell) { const [r, c] = b.dataset.cell.split(",").map(Number); return place(r, c); }
  if (b.dataset.do === "fresh") newBoard(seedWords(), size);
});
document.addEventListener("submit", (e) => {
  if (e.target.id !== "seedform") return;
  e.preventDefault();
  newBoard($("seed").value.trim() || seedWords(), +$("size").value);
});

frame.setup({ seats: false, score: true, deck: true, scoreTitle: "Boards", deckTitle: "This board", redraw: render });
frame.clearLog();
newBoard(seed, size);
