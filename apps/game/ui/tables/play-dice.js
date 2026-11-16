/* The dice tray: dice's notation (2d6, 1d20+3, 1d8+1d6) and dice5e's keeping
   (4d6kh3, 2d20kl1, adv, dis), read as play-dice and play-dice5e read them
   (adapters/stdlib/play-dice, play-dice5e): up to 100 dice of 2 to 1000
   sides; every die is thrown, kept or not; among equal faces the first
   thrown is kept. On the record the faces come from the record's tip; here,
   from the browser. */
const MAX_DICE = 100, MAX_SIDES = 1000;
const SHORT = { adv: "2d20kh1", dis: "2d20kl1" };
const TERM = /([+-]?)(?:(\d*)d(\d+)(?:k([hl])(\d+))?|(\d+))/gi;
const BAD = "that isn't dice notation: try 2d6+1, 4d6kh3, adv+5, 1d8+1d6.";
const QUICK = ["2d6", "1d20", "2d6+1", "4d6kh3", "adv+5", "dis", "3d8+2", "1d100", "1d8+1d6"];

function parse(text) {
  let t = text.trim().toLowerCase().replace(/\s*([+-])\s*/g, "$1").replace(/\b(adv|dis)\b/g, (m) => SHORT[m]);
  if (!t || t.replace(TERM, "")) throw new Error(BAD);
  const terms = []; let add = 0, pos = 0;
  for (const m of t.matchAll(TERM)) {
    if (m.index !== pos || (pos && !m[1])) throw new Error(BAD);
    pos = m.index + m[0].length;
    const sign = m[1] === "-" ? -1 : 1;
    if (m[6]) { add += sign * +m[6]; continue; }
    const count = +(m[2] || 1), sides = +m[3];
    if (!(count >= 1 && count <= MAX_DICE && sides >= 2 && sides <= MAX_SIDES)) throw new Error(`${count}d${sides}: up to ${MAX_DICE} dice of 2 to ${MAX_SIDES} sides.`);
    const keep = m[4] || "", k = +(m[5] || count);
    if (!(k >= 1 && k <= count)) throw new Error(`${count}d${sides}k${keep}${k}: keep 1 to ${count}.`);
    terms.push({ sign, count, sides, keep, k });
  }
  if (!terms.length) throw new Error("that rolls no dice.");
  return { terms, add };
}
function keptOf(faces, keep, k) {
  if (!keep) return faces.map((_, i) => i);
  const order = faces.map((f, i) => i).sort((a, b) => (keep === "h" ? faces[b] - faces[a] : faces[a] - faces[b]) || a - b);
  return order.slice(0, k).sort((a, b) => a - b);
}
function throwDice(text) {
  const { terms, add } = parse(text);
  let total = add;
  const groups = terms.map((t) => {
    const faces = Array.from({ length: t.count }, () => 1 + rnd(t.sides));
    const kept = keptOf(faces, t.keep, t.k);
    total += t.sign * kept.reduce((n, i) => n + faces[i], 0);
    return { ...t, faces, kept };
  });
  const lo = terms.reduce((n, t) => n + t.sign * (t.sign > 0 ? t.k : t.k * t.sides), add);
  const hi = terms.reduce((n, t) => n + t.sign * (t.sign > 0 ? t.k * t.sides : t.k), add);
  return { text, groups, add, total, lo, hi };
}
/* as the record says it: 4d6kh3: [6, 2, 5, 3] keep 6 + 5 + 3 = 14 */
function sayRoll(r) {
  const parts = r.groups.map((g, gi) => {
    const keptFaces = g.kept.map((i) => g.faces[i]);
    const body = g.keep ? `[${g.faces.join(", ")}] keep ${keptFaces.join(" + ")}` : keptFaces.join(" + ");
    return (gi ? (g.sign < 0 ? " - " : " + ") : g.sign < 0 ? "- " : "") + (g.sign < 0 || r.groups.length > 1 ? `(${body})` : body);
  });
  return `${r.text}: ${parts.join("")}${r.add ? (r.add > 0 ? ` + ${r.add}` : ` - ${-r.add}`) : ""} = ${r.total}`;
}

let text = "2d6", last = null, history = [], n = 0;

function roll() {
  try { last = throwDice(text); }
  catch (e) { return frame.refuse(e.message); }
  n++;
  if (n === 1) frame.clearLog();
  history.unshift({ label: String(n), cells: [esc(last.text), `<b>${last.total}</b>`] });
  frame.log(esc(sayRoll(last)));
  render(true);
}

function render(fresh) {
  const shown = last;
  frame.stage(`
    <form id="tray" class="actions" style="gap:8px" autocomplete="off">
      <label for="notation" class="count" style="font-size:.85rem">Dice</label>
      <input id="notation" value="${esc(text)}" spellcheck="false" style="font:inherit;font-family:var(--mono);font-size:1.1rem;width:12ch;padding:8px 10px;border-radius:9px;border:2px solid var(--edge);background:#0004;color:var(--chalk)">
      <button class="btn" type="submit">Roll</button>
    </form>
    <div class="actions" style="gap:6px">${QUICK.map((q) => `<button class="toggle" style="border-color:var(--edge)" data-quick="${esc(q)}" aria-pressed="${q === text}">${esc(q)}</button>`).join("")}</div>
    ${shown ? `
      <div style="display:grid;gap:22px;justify-items:center;padding:8px 0">
        ${shown.groups.map((g, gi) => `<div style="display:grid;gap:6px;justify-items:center">
            <span class="count">${gi || g.sign < 0 ? (g.sign < 0 ? "minus " : "plus ") : ""}${g.count}d${g.sides}${g.keep ? `, keep the ${g.keep === "h" ? "highest" : "lowest"} ${g.k}` : ""}</span>
            <div class="dice-row" style="gap:10px 12px;row-gap:22px;max-width:640px;padding-bottom:8px">${g.faces.map((f, i) => polyDieHTML(g.sides, f, { dim: !g.kept.includes(i), roll: fresh, size: "" })).join("")}</div>
          </div>`).join("")}
        ${shown.add ? `<span class="count">${shown.add > 0 ? "plus" : "minus"} ${Math.abs(shown.add)}</span>` : ""}
        <div style="font-family:var(--lid-font);font-size:3.4rem;line-height:1">${shown.total}</div>
        <div class="count">${esc(sayRoll(shown))}</div>
      </div>` : `<p class="count" style="font-size:.95rem">Type dice, or pick one above, and roll.</p>`}`);
  frame.status("");
  frame.actions("");
  frame.score({ you: -1, head: "Roll", cols: ["Dice", "Total"], rows: history.slice(0, 30), note: "The last thirty rolls, newest first. Kept only while this page is open.", empty: "Your rolls go here." });
  const dropped = shown ? shown.groups.reduce((a, g) => a + g.count - g.kept.length, 0) : 0;
  frame.deck(shown ? [["Dice thrown", shown.groups.reduce((a, g) => a + g.count, 0)], ["Kept", shown.groups.reduce((a, g) => a + g.kept.length, 0)], ["Dropped", dropped], ["Lowest it can be", shown.lo], ["Highest it can be", shown.hi]] : [["Dice thrown", "–"]],
    "Up to 100 dice of 2 to 1000 sides a term. kh keeps the highest, kl the lowest; adv and dis are 2d20 keeping one.");
}

document.addEventListener("submit", (e) => {
  if (e.target.id !== "tray") return;
  e.preventDefault(); text = $("notation").value.trim() || text; roll();
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-quick]"); if (!b) return;
  text = b.dataset.quick; roll();
});

frame.setup({ seats: false, score: true, deck: true, hints: false, scoreTitle: "Rolls", deckTitle: "This roll", redraw: render });
frame.log("Nothing rolled yet. Each roll is listed here as the record writes it.");
render();
