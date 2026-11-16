/* Tarot, as play-tarot draws it on the record (adapters/stdlib/play-tarot):
   N cards (three unasked) from the full deck of 78 without replacement, each
   upright or reversed by a coin. What the cards mean is yours: the draw says
   nothing about them, so neither does this page. */
const MAJORS = ["The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor", "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit", "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance", "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World"];
const RANKS = ["Ace", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"];
const SUITS = ["Wands", "Cups", "Swords", "Pentacles"];
const DECK = [...MAJORS.map((n, i) => ({ major: i, name: n })), ...SUITS.flatMap((s) => RANKS.map((r, i) => ({ suit: s, rank: i, name: `${r} of ${s}` })))];
const ROMAN = (n) => (n === 0 ? "0" : ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"][n]);
const SIZES = [1, 3, 5, 7];

const ICON = {
  Wands: '<path d="M12 2v20M9 5l3-3 3 3" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
  Cups: '<path d="M5 4h14c0 6-3 9-7 9s-7-3-7-9zM12 13v6M8 21h8" stroke="currentColor" stroke-width="2" fill="none" stroke-linejoin="round"/>',
  Swords: '<path d="M12 2v15M7 17h10M12 17v5" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
  Pentacles: '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 5l2 6h6l-5 3.6 2 6-5-3.8-5 3.8 2-6L4 11h6z" fill="currentColor" transform="scale(.62) translate(7.4 7.6)"/>',
};
const SUIT_TINT = { Wands: "#b8562b", Cups: "#2f6fa8", Swords: "#4a4f5c", Pentacles: "#8a6a12" };
const icon = (s, px) => `<svg viewBox="0 0 24 24" width="${px}" height="${px}" aria-hidden="true">${ICON[s]}</svg>`;

function face(c) {
  if (c.major !== undefined) return `<span style="font-family:var(--lid-font);font-size:1.6rem;line-height:1">${ROMAN(c.major)}</span><span style="font-size:.5rem;letter-spacing:.3em;opacity:.6">✦ ✦ ✦</span><span style="font-family:var(--prose);font-size:.82rem;font-weight:500;line-height:1.15">${esc(c.name)}</span>`;
  const n = c.rank + 1;
  const art = n <= 10 ? `<span style="display:flex;flex-wrap:wrap;justify-content:center;gap:2px;max-width:70px">${Array.from({ length: n }, () => icon(c.suit, n > 6 ? 14 : 18)).join("")}</span>` : `<span style="font-family:var(--lid-font);font-size:1.5rem">${RANKS[c.rank][0]}${c.rank === 11 ? "n" : ""}</span>${icon(c.suit, 22)}`;
  return `${art}<span style="font-family:var(--prose);font-size:.78rem;font-weight:500;line-height:1.15">${esc(c.name)}</span>`;
}
function tarotCard(d, i, shown) {
  const c = d.card;
  const base = "width:112px;aspect-ratio:3/5;border-radius:9px;display:grid;place-items:center;align-content:center;gap:8px;text-align:center;padding:10px 8px;box-shadow:0 6px 14px -6px #000c;transition:transform .45s ease";
  if (!shown) return `<div style="${base};background:repeating-linear-gradient(45deg,var(--lid) 0 6px,color-mix(in srgb,var(--lid) 50%,#f1d9a0) 6px 9px);border:4px solid #f1d9a0" aria-label="card ${i + 1}, face down"></div>`;
  const deck = frame.deckArt();
  if (deck) { // the fetched scans, named as the fetch names them: major-18, cups-13
    const key = c.major !== undefined ? `major-${String(c.major).padStart(2, "0")}` : `${c.suit.toLowerCase()}-${String(c.rank + 1).padStart(2, "0")}`;
    return `<div class="pc img" style="--w:112px;width:112px;aspect-ratio:3/5;border-radius:6px;box-shadow:0 6px 14px -6px #000c;transition:transform .45s ease;${d.reversed ? "transform:rotate(180deg)" : ""}" role="img" aria-label="${esc(c.name)}${d.reversed ? ", reversed" : ""}">${artHTML(`decks/${deck.id}/${key}.${deck.ext}`, c.name)}</div>`;
  }
  const tint = c.suit ? SUIT_TINT[c.suit] : "#3a2a10";
  return `<div style="${base};background:#f8efd8;color:${tint};border:2px solid #d9c48f;${d.reversed ? "transform:rotate(180deg)" : ""}" role="img" aria-label="${esc(c.name)}${d.reversed ? ", reversed" : ""}">${face(c)}</div>`;
}

let size = 3, spread = [], shown = 0, draws = 0, busy = false;

async function draw() {
  if (busy) return; busy = true;
  spread = shuffle(DECK).slice(0, size).map((card) => ({ card, reversed: rnd(2) === 1 }));
  shown = 0; draws++; if (draws === 1) frame.clearLog(); render();
  for (let i = 0; i < spread.length; i++) { await wait(420); shown = i + 1; render(); }
  frame.log(`<b>Draw ${draws}</b>, ${size} card${size > 1 ? "s" : ""}:<br>${spread.map((d, i) => `${i + 1}. ${esc(d.card.name)}${d.reversed ? ", reversed" : ""}`).join("<br>")}`);
  busy = false; render();
}

function render() {
  frame.status(spread.length ? (busy ? "Turning them over…" : `${spread.length} card${spread.length > 1 ? "s" : ""}, read left to right.`) : "Choose how many cards, then draw.");
  frame.stage(spread.length
    ? `<div style="display:flex;flex-wrap:wrap;gap:16px;justify-content:center;padding:10px 0">${spread.map((d, i) => `<div style="display:grid;gap:8px;justify-items:center"><span class="count">${i + 1}</span>${tarotCard(d, i, i < shown)}<span class="count" style="min-height:1.2em">${i < shown ? (d.reversed ? "reversed" : "upright") : ""}</span></div>`).join("")}</div>`
    : `<div style="display:flex;gap:10px;justify-content:center;padding:20px 0">${[0, 1, 2].map((i) => tarotCard({ card: DECK[0] }, i, false)).join("")}</div>`);
  frame.actions(`<div role="group" aria-label="How many cards" style="display:flex;gap:6px">${SIZES.map((n) => `<button class="toggle" style="border-color:var(--edge)" data-size="${n}" aria-pressed="${n === size}">${n}</button>`).join("")}</div>
    <button class="btn" data-do="draw" ${busy ? "disabled" : ""}>${spread.length ? "Draw again" : "Draw"} ${size}</button>`);
  const majors = spread.filter((d) => d.card.major !== undefined).length;
  frame.deck([["The deck", 78], ["Major arcana", 22], ["Minor arcana", "56, 14 a suit"], ["Suits", SUITS.join(", ")], ["This draw", spread.length ? `${majors} major, ${spread.length - majors} minor` : "–"], ["Left in the deck", 78 - spread.length]],
    "Each card is dealt once, without replacement, and a coin turns it upright or reversed. What they mean is yours.");
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.disabled) return;
  if (b.dataset.size) { size = +b.dataset.size; render(); }
  else if (b.dataset.do === "draw") draw();
});

frame.setup({ seats: false, score: false, deck: true, hints: false, redraw: render });
frame.log("Nothing drawn yet. Each draw is listed here as the record lists it.");
render();
