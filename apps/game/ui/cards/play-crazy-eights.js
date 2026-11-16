/* Crazy Eights, as play-crazy-eights plays it on the record
   (adapters/stdlib/play-crazy-eights): four seats, five cards each, one turned
   up to start the pile, the rest the stock. Match the suit to follow or the top
   card's rank; an 8 is wild and names the suit. Nothing to play: draw one and go
   again; nothing to play and no stock: pass. First out wins; four passes in a row
   with no stock and the hand is stalled. North plays first; you sit south. */
const HAND = 5, STALL = 4;
const legal = (hand, top, suit) => hand.filter((c) => c.r === 8 || c.s === suit || c.r === top.r);

let G, busy = false;

function newGame() { G = { rows: [], wins: [0, 0, 0, 0], handNo: 0 }; frame.clearLog(); deal(); }
function deal() {
  const d = shuffle(deck52());
  const hands = [0, 1, 2, 3].map((i) => d.slice(i * HAND, i * HAND + HAND));
  const stock = d.slice(HAND * 4);
  const top = stock.shift();
  Object.assign(G, { hands, stock, top, pile: [top], suit: top.s, turn: 0, passes: 0, winner: null, over: false, pick8: null });
  frame.log(`<b>Hand ${G.handNo + 1}.</b> ${said(top)} turned up; ${SUIT_NAME[top.s]} to follow.`);
  render(); run();
}
const can = (seat) => legal(G.hands[seat], G.top, G.suit);

function playCard(seat, card, call) {
  G.hands[seat] = G.hands[seat].filter((c) => !sameCard(c, card));
  G.top = card; G.pile.push(card); G.suit = card.r === 8 ? call : card.s; G.passes = 0;
  frame.log(`<b>${SEAT_NAME(seat)}</b> play${seat === YOU ? "" : "s"} ${said(card)}${card.r === 8 ? `, and name${seat === YOU ? "" : "s"} ${SUIT_NAME[call]}` : ""}.`);
  if (!G.hands[seat].length) return end(seat);
  G.turn = (seat + 1) % 4;
}
function drawCard(seat) {
  const c = G.stock.pop(); G.hands[seat].push(c);
  frame.log(`${SEAT_NAME(seat)} draw${seat === YOU ? "" : "s"} a card${seat === YOU ? `: ${said(c)}` : ""}.`);
}
function passTurn(seat) {
  G.passes++; frame.log(`${SEAT_NAME(seat)} pass${seat === YOU ? "" : "es"}: nothing to play and no stock.`);
  G.turn = (seat + 1) % 4;
  if (G.passes >= STALL) end(null);
}
function end(winner) {
  G.over = true; G.winner = winner;
  if (winner !== null) G.wins[winner]++;
  G.rows.push({ label: String(G.handNo + 1), cells: G.hands.map((h, i) => (i === winner ? "out ★" : `${h.length} left`)) });
  frame.log(winner === null ? "<b>Stalled.</b> Four passes, no stock: nobody wins." : `<b>${SEAT_NAME(winner)} ${winner === YOU ? "are" : "is"} out, and win${winner === YOU ? "" : "s"} the hand.</b>`);
}

/* the other seats */
function most(hand) {
  const n = { C: 0, D: 0, H: 0, S: 0 }; hand.forEach((c) => { if (c.r !== 8) n[c.s]++; });
  return "CDHS".split("").reduce((a, b) => (n[b] > n[a] ? b : a));
}
function botTurn(seat) {
  const ok = can(seat);
  if (ok.length) {
    const plain = ok.filter((c) => c.r !== 8);
    if (plain.length) { const s = most(G.hands[seat]); const pick = plain.find((c) => c.s === s) || plain[0]; return playCard(seat, pick); }
    const eight = ok[0]; return playCard(seat, eight, most(G.hands[seat].filter((c) => !sameCard(c, eight))));
  }
  if (G.stock.length) return drawCard(seat);
  passTurn(seat);
}
async function run() {
  if (busy) return; busy = true;
  while (!G.over && G.turn !== YOU) { render(); await wait(560); botTurn(G.turn); }
  busy = false; render();
}

/* ---------- drawing ---------- */
function render() {
  for (const i of [0, 1, 3]) frame.seat(i, G.hands[i], { turn: !G.over && G.turn === i, meta: `${G.hands[i].length} cards · ${G.wins[i]} won` });
  const mineTurn = !G.over && G.turn === YOU && !busy;
  const ok = mineTurn && !G.pick8 ? can(YOU) : [];
  const mustDraw = mineTurn && !ok.length && G.stock.length && !G.pick8;
  const red = G.suit === "H" || G.suit === "D";
  frame.middle(`<div class="pile">
      <div style="display:grid;gap:4px;justify-items:center">${G.stock.length ? (mustDraw ? `<button class="pc back big" data-do="draw" aria-label="Draw from the stock"></button>` : cardHTML(null, { back: true, size: "big" })) : `<div class="pc big" style="opacity:.15"></div>`}<span class="count">stock ${G.stock.length}</span></div>
      <div style="display:grid;gap:4px;justify-items:center">${cardHTML(G.top, { size: "big" })}<span class="count">pile ${G.pile.length}</span></div>
    </div>
    <div class="count" style="font-size:.85rem">to follow: <b style="font-size:1.2rem;color:${red ? "#ff8f7a" : "var(--chalk)"}">${SUIT_GLYPH[G.suit]}</b> ${SUIT_NAME[G.suit]}</div>`);
  frame.mine(sortHand(G.hands[YOU].slice()), { can: (c) => ok.some((x) => sameCard(x, c)), chosen: (c) => G.pick8 && sameCard(c, G.pick8), turn: !G.over && G.turn === YOU, meta: `${G.hands[YOU].length} cards · ${G.wins[YOU]} won` });

  if (G.over) {
    frame.status(G.winner === null ? "<b>Stalled.</b> Nobody wins this hand." : `<b>${SEAT_NAME(G.winner)} ${G.winner === YOU ? "went" : "goes"} out.</b>`);
    frame.actions(`<button class="btn" data-do="next">Deal hand ${G.handNo + 2}</button>`);
  } else if (G.pick8) {
    frame.status("<b>An 8 is wild.</b> Name the suit to follow.");
    frame.actions(`<div class="suit-pick">${"CDHS".split("").map((s) => `<button class="${s === "H" || s === "D" ? "red" : ""}" data-suit="${s}" aria-label="${SUIT_NAME[s]}">${SUIT_GLYPH[s]}</button>`).join("")}</div><button class="btn ghost" data-do="unpick">Keep the 8</button>`);
  } else if (mineTurn) {
    frame.status(ok.length ? `<b>Your turn.</b> Play a ${SUIT_NAME[G.suit].replace(/s$/, "")}, a ${RANK_TEXT(G.top.r)}, or an 8.` : G.stock.length ? "<b>Nothing to play.</b> Draw one, and go again." : "<b>Nothing to play, and no stock.</b> Pass.");
    frame.actions(!ok.length ? (G.stock.length ? `<button class="btn" data-do="draw">Draw a card</button>` : `<button class="btn" data-do="pass">Pass</button>`) : "");
  } else { frame.status(`${SEAT_NAME(G.turn)} to play…`); frame.actions(""); }

  const best = Math.max(...G.wins);
  frame.score({ cols: SEATS.map((s, i) => SEAT_NAME(i)), rows: G.rows, totals: G.wins.map((w) => `${w} won`), lead: best ? G.wins.map((w, i) => (w === best ? i : -1)) : [],
    note: "The record names who went out, not points: the sheet counts hands won, and the cards each seat still held. Kept only while this page is open.", empty: "Who goes out, and what the rest held." });
  frame.deck([["Stock", G.stock.length], ["Pile", G.pile.length], ["In hands", G.hands.reduce((n, h) => n + h.length, 0)], ["Top card", said(G.top)], ["Suit to follow", SUIT_NAME[G.suit]], ["Passes in a row", `${G.passes} of ${STALL}`]],
    "52 cards, five to a seat, one turned up, the rest the stock. Draws come off the stock one at a time.");
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.disabled) return;
  if (b.dataset.card && !G.over && G.turn === YOU && !busy) {
    const c = G.hands[YOU].find((x) => cardName(x) === b.dataset.card);
    if (c.r === 8) { G.pick8 = c; return render(); }
    playCard(YOU, c); render(); return run();
  }
  if (b.dataset.suit && G.pick8) { const c = G.pick8; G.pick8 = null; playCard(YOU, c, b.dataset.suit); render(); return run(); }
  const d = b.dataset.do;
  if (d === "unpick") { G.pick8 = null; render(); }
  else if (d === "draw" && G.turn === YOU && !can(YOU).length && G.stock.length) { drawCard(YOU); render(); }
  else if (d === "pass" && G.turn === YOU) { passTurn(YOU); render(); run(); }
  else if (d === "next") { G.handNo++; deal(); }
});

frame.setup({ seats: true, score: true, deck: true, scoreTitle: "Scoresheet · who went out", redraw: render });
newGame();
