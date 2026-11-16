/* Liar's Dice, as play-liars-dice plays it on the record
   (adapters/stdlib/play-liars-dice): four seats, five dice each. Each round
   every seat still in throws its cup. A bid says there are at least that many
   of a face on the whole table, ones wild except in a bid on ones. The opener
   bids; each seat in turn raises (more dice, or as many of a higher face) or
   calls the last bid. On a call the face is counted: if the bid holds, the
   caller loses a die; if not, the bidder does. A seat with none left is out;
   the loser opens the next round, or the next seat still in; the last seat
   with dice wins. North opens the first round; you sit south. */
const EACH = 5;
const counted = (faces, face) => faces.filter((d) => d === face || (face !== 1 && d === 1)).length;
const above = (bid, q, f, total) => { const [cq, cf] = bid ? [bid.q, bid.f] : [0, 0]; return q >= 1 && q <= total && f >= 1 && f <= 6 && (q > cq || (q === cq && f > cf)); };
const FACE_NAME = (f, n) => (n === 1 ? ["", "one", "two", "three", "four", "five", "six"][f] : ["", "ones", "twos", "threes", "fours", "fives", "sixes"][f]);
const bidSaid = (b) => `${b.q} ${FACE_NAME(b.f, b.q)}`;

let G, busy = false;
let pick = { q: 1, f: 2 };

const seatsIn = () => [0, 1, 2, 3].filter((s) => G.dice[s] > 0);
const total = () => G.dice.reduce((a, b) => a + b, 0);
const after = (s) => { for (let k = 1; k <= 4; k++) if (G.dice[(s + k) % 4] > 0) return (s + k) % 4; return s; };

function newGame() {
  G = { dice: [EACH, EACH, EACH, EACH], round: 0, opener: 0, rows: [], over: false };
  frame.clearLog();
  frame.log("<b>A new game.</b> Five dice each; the last seat with dice wins.");
  startRound();
}
function startRound() {
  G.round++;
  G.cups = {}; for (const s of seatsIn()) G.cups[s] = Array.from({ length: G.dice[s] }, () => 1 + rnd(6));
  G.bid = null; G.bidder = null; G.turn = G.opener; G.last = null; G.fresh = true;
  pick = { q: 1, f: 2 };
  frame.log(`Round ${G.round}: every cup thrown. ${SEAT_NAME(G.opener)} open${G.opener === YOU ? "" : "s"}.`);
  render(); run();
}

function bid(seat, q, f) {
  G.bid = { q, f }; G.bidder = seat; G.turn = after(seat); G.fresh = false;
  frame.log(`<b>${SEAT_NAME(seat)}</b> bid${seat === YOU ? "" : "s"} ${bidSaid(G.bid)}.`);
}
function call(seat) {
  const { q, f } = G.bid;
  const all = seatsIn().flatMap((s) => G.cups[s]);
  const count = counted(all, f);
  const loser = count >= q ? seat : G.bidder;
  G.dice[loser]--;
  G.last = { q, f, count, caller: seat, bidder: G.bidder, loser, cups: G.cups };
  frame.log(`<b>${SEAT_NAME(seat)}</b> call${seat === YOU ? "" : "s"} ${SEAT_NAME(G.bidder)}'s ${bidSaid(G.bid)}: ${count} on the table. ${count >= q ? "The bid holds" : "It doesn't"}; <b>${SEAT_NAME(loser)}</b> lose${loser === YOU ? "" : "s"} a die.`);
  G.rows.push({ label: `${G.round} · ${q}×${f}`, cells: G.dice.map((d, i) => (i === loser ? `${d} ▾` : d)) });
  G.cups = null;
  if (seatsIn().length === 1) { G.over = true; frame.log(`<b>${SEAT_NAME(seatsIn()[0])} win${seatsIn()[0] === YOU ? "" : "s"} the game.</b>`); }
  else G.opener = G.dice[loser] ? loser : after(loser);
}

/* the other seats: they count their own cup, guess the rest, and bluff a little */
function expect(seat, f) { const own = counted(G.cups[seat], f); return own + (total() - G.cups[seat].length) * (f === 1 ? 1 / 6 : 1 / 3); }
function botTurn(seat) {
  const nerve = (rnd(100) - 50) / 100; // -0.5 .. 0.5
  if (!G.bid) {
    let best = 2; for (let f = 2; f <= 6; f++) if (counted(G.cups[seat], f) > counted(G.cups[seat], best)) best = f;
    return bid(seat, Math.max(1, Math.round(expect(seat, best) - 1 + nerve)), best);
  }
  if (G.bid.q > expect(seat, G.bid.f) + 0.9 + nerve) return call(seat);
  let choice = null;
  for (let f = 1; f <= 6; f++) {
    const q = f > G.bid.f ? G.bid.q : G.bid.q + 1;
    if (!above(G.bid, q, f, total())) continue;
    const score = expect(seat, f) - q + rnd(10) / 25;
    if (!choice || score > choice.score) choice = { q, f, score };
  }
  if (!choice || choice.score < -1.1 + nerve) return call(seat);
  bid(seat, choice.q, choice.f);
}
async function run() {
  if (busy) return; busy = true;
  while (!G.over && G.cups && G.turn !== YOU) { render(); await wait(800); botTurn(G.turn); }
  busy = false;
  if (G.cups && G.bid) pick = { q: G.bid.q, f: G.bid.f };
  render();
}

/* ---------- drawing ---------- */
function cupHTML(seat, open, mark) {
  const faces = G.cups ? G.cups[seat] : G.last && G.last.cups[seat];
  if (!faces) return `<div class="count">out</div>`;
  const f = G.last && !G.cups ? G.last.f : null;
  return `<div class="dice-row" style="gap:4px">${faces.map((d) => dieHTML(d, { size: "small", hidden: !open, mark: mark && f && (d === f || (f !== 1 && d === 1)) })).join("")}</div>`;
}
function render() {
  const reveal = !G.cups; // after a call every cup is lifted
  for (const i of [0, 1, 3]) frame.seatAny(i, G.dice[i] || (G.last && G.last.cups[i]) ? cupHTML(i, frame.open || reveal, reveal) : `<div class="count">out of dice</div>`,
    { turn: !G.over && G.cups && G.turn === i, out: !G.dice[i] && !(reveal && G.last && G.last.cups[i]), meta: `${G.dice[i]} dice` });

  // the middle: the bid standing, or what the call found
  if (G.cups) {
    frame.middle(G.bid
      ? `<div class="count">${esc(SEAT_NAME(G.bidder))} bid${G.bidder === YOU ? "" : "s"}</div><div class="dice-row"><span style="font-family:var(--lid-font);font-size:2.2rem">${G.bid.q} ×</span>${dieHTML(G.bid.f, { size: "big" })}</div><div class="count">${total()} dice on the table</div>`
      : `<div class="count" style="font-size:.95rem">No bid yet.<br>${esc(SEAT_NAME(G.opener))} open${G.opener === YOU ? "" : "s"}.</div><div class="count">${total()} dice on the table</div>`);
  } else if (G.last) {
    const L = G.last;
    frame.middle(`<div class="count">${esc(SEAT_NAME(L.caller))} called ${esc(SEAT_NAME(L.bidder))}'s</div>
      <div class="dice-row"><span style="font-family:var(--lid-font);font-size:2rem">${L.q} ×</span>${dieHTML(L.f, { size: "big" })}</div>
      <div style="font-weight:800;font-size:1.1rem">${L.count} on the table</div>
      <div class="count" style="font-size:.9rem">${L.count >= L.q ? "The bid holds." : "It doesn't."} ${esc(SEAT_NAME(L.loser))} lose${L.loser === YOU ? "" : "s"} a die.</div>`);
  }

  // your cup
  const mineOpen = G.cups ? G.cups[YOU] : null;
  frame.mineAny(G.dice[YOU] || (reveal && G.last && G.last.cups[YOU])
    ? `<div class="dice-row">${(mineOpen || (G.last && G.last.cups[YOU]) || []).map((d) => dieHTML(d, { roll: G.fresh && !busy, mark: reveal && G.last && (d === G.last.f || (G.last.f !== 1 && d === 1)) })).join("")}</div>`
    : `<div class="count">You're out of dice.</div>`, { turn: !G.over && G.cups && G.turn === YOU, meta: `${G.dice[YOU]} dice` });

  // what you can do
  const mine = !G.over && G.cups && G.turn === YOU && !busy;
  if (G.over) {
    frame.status(`<b>${SEAT_NAME(seatsIn()[0])} win${seatsIn()[0] === YOU ? "" : "s"}.</b>`);
    frame.actions(`<button class="btn" data-do="new">New game</button>`);
  } else if (!G.cups) {
    frame.status("Every cup is lifted.");
    frame.actions(`<button class="btn" data-do="next">Next round</button>`);
  } else if (mine) {
    const held = counted(G.cups[YOU], pick.f);
    frame.status(frame.hints
      ? `<b>${G.bid ? "Raise or call." : "Your opening bid."}</b> You hold ${held} ${FACE_NAME(pick.f, held)}${pick.f !== 1 ? ", ones counted" : ""}. ${G.bid ? `A raise: more than ${G.bid.q}, or ${G.bid.q} of a face above ${FACE_NAME(G.bid.f, 1)}.` : ""}`
      : `<b>${G.bid ? "Your turn." : "Your opening bid."}</b>`);
    const ok = (f) => above(G.bid, pick.q, f, total());
    frame.actions(`
      <div class="actions" style="gap:8px">
        <button class="btn ghost" data-q="-1" aria-label="One fewer">−</button>
        <span style="font-family:var(--lid-font);font-size:1.6rem;min-width:2ch;text-align:center" aria-live="polite">${pick.q}</span>
        <button class="btn ghost" data-q="1" aria-label="One more">+</button>
        <span style="opacity:.6">×</span>
        ${[1, 2, 3, 4, 5, 6].map((f) => `<button data-f="${f}" aria-label="${FACE_NAME(f, 2)}" aria-pressed="${f === pick.f}" style="border-radius:8px;padding:2px;${f === pick.f ? "outline:3px solid var(--go)" : ""};${frame.hints && !ok(f) ? "opacity:.35" : ""}">${dieHTML(f, { size: "small" })}</button>`).join("")}
      </div>
      <button class="btn" data-do="bid">Bid ${pick.q} ${FACE_NAME(pick.f, pick.q)}</button>
      <button class="btn ghost" data-do="call">Call it</button>`);
  } else {
    frame.status(`${SEAT_NAME(G.turn)} ${G.bid ? "is thinking…" : "opens…"}`);
    frame.actions("");
  }

  const most = Math.max(...G.dice);
  frame.score({ head: "Round", cols: SEATS.map((s, i) => SEAT_NAME(i)), rows: G.rows, totals: G.dice.map((d) => `${d}`), lead: G.rows.length ? G.dice.map((d, i) => (d === most ? i : -1)) : [],
    note: "Dice left after each round; ▾ marks who lost one. The last seat with dice wins. Kept only while this page is open.", empty: "Each call's loser goes here." });
  frame.deck([["Dice on the table", total()], ["In your cup", G.dice[YOU]], ["Round", G.round], [G.cups ? "Opened by" : "Opens next", SEAT_NAME(G.opener)], ["Standing bid", G.bid ? bidSaid(G.bid) : "none"], ["Seats still in", seatsIn().length]],
    "Ones are wild, except in a bid on ones. A bid counts every cup on the table, yours too.");
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.disabled) return;
  const mine = !G.over && G.cups && G.turn === YOU && !busy;
  if (b.dataset.q && mine) { pick.q = Math.max(1, Math.min(total(), pick.q + +b.dataset.q)); return render(); }
  if (b.dataset.f && mine) { pick.f = +b.dataset.f; return render(); }
  const d = b.dataset.do;
  if (d === "bid" && mine) {
    if (!above(G.bid, pick.q, pick.f, total())) return frame.refuse(G.bid ? "a raise is more dice, or as many of a higher face." : `a bid is 1 to ${total()} dice.`);
    bid(YOU, pick.q, pick.f); render(); return run();
  }
  if (d === "call" && mine) {
    if (!G.bid) return frame.refuse("there's no bid to call: the opener bids.");
    call(YOU); return render();
  }
  if (d === "next") { startRound(); }
  else if (d === "new") newGame();
});

frame.setup({ seats: true, score: true, deck: true, scoreTitle: "Scoresheet · dice left", deckTitle: "The cups", redraw: render });
newGame();
