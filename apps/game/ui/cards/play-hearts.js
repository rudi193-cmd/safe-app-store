/* Hearts, as play-hearts plays it on the record (adapters/stdlib/play-hearts):
   four seats, passes left, right, across, then held; the 2C leads; follow suit;
   hearts not led until broken unless nothing else; no points on the first trick
   unless nothing else; a heart a point, the QS thirteen; all 26 shoots the moon;
   at 100 the game ends and the lowest score wins. You sit south. */
const WAYS = ["left", "right", "across", "held"];
const END = 100;
const isQS = (c) => c.r === 12 && c.s === "S";
const isTwoClubs = (c) => c.r === 2 && c.s === "C";
const points = (c) => (c.s === "H" ? 1 : isQS(c) ? 13 : 0);
const target = (seat, way) => [(seat + 1) % 4, (seat + 3) % 4, (seat + 2) % 4, seat][way];

function legal(hand, trick, broken, first) {
  if (!trick.length) {
    if (first && hand.some(isTwoClubs)) return hand.filter(isTwoClubs);
    if (!broken) { const plain = hand.filter((c) => c.s !== "H"); return plain.length ? plain : hand.slice(); }
    return hand.slice();
  }
  const led = trick[0][1].s;
  const follow = hand.filter((c) => c.s === led);
  if (follow.length) return follow;
  if (first) { const safe = hand.filter((c) => points(c) === 0); return safe.length ? safe : hand.slice(); }
  return hand.slice();
}

/* which rule a card breaks: the rule, never which card would do */
function broken(card) {
  const hand = G.hands[YOU], first = G.tricks === 0;
  if (!G.trick.length) {
    if (first) return "the 2♣ leads the first trick.";
    return "hearts can't be led until one has been played.";
  }
  if (card.s !== G.trick[0][1].s && hand.some((c) => c.s === G.trick[0][1].s)) return "follow the suit led.";
  if (first && points(card)) return "no points on the first trick.";
  return "the rules don't allow that card now.";
}

let G; // the game
let busy = false, running = false; // busy: a full trick being taken; running: the other seats playing

function newGame() {
  G = { scores: [0, 0, 0, 0], rows: [], handNo: 0, over: false };
  frame.clearLog();
  frame.log("<b>A new game.</b> First to 100 ends it; the lowest score wins.");
  deal();
}
function deal() {
  const d = shuffle(deck52());
  Object.assign(G, {
    hands: [0, 1, 2, 3].map((i) => sortHand(d.slice(i * 13, i * 13 + 13))),
    taken: [[], [], [], []], trick: [], broken: false, tricks: 0, chosen: [], last: null,
  });
  G.way = G.handNo % 4;
  if (G.way === 3) { G.phase = "play"; lead(); frame.log(`Hand ${G.handNo + 1}: dealt, and held: no passing.`); render(); run(); }
  else { G.phase = "pass"; frame.log(`Hand ${G.handNo + 1}: dealt. Pass three ${WAYS[G.way]}.`); render(); }
}
const lead = () => { G.leader = G.hands.findIndex((h) => h.some(isTwoClubs)); };
const toPlay = () => (G.leader + G.trick.length) % 4;

/* the other seats: a plain, honest player each */
function botPass(hand) {
  const risk = (c) => (isQS(c) ? 100 : c.s === "S" && c.r > 12 ? 90 : c.s === "H" ? 20 + c.r : c.r);
  return hand.slice().sort((a, b) => risk(b) - risk(a)).slice(0, 3);
}
function botCard(seat) {
  const hand = G.hands[seat], ok = legal(hand, G.trick, G.broken, G.tricks === 0);
  const low = (xs) => xs.reduce((a, b) => (b.r < a.r ? b : a));
  const high = (xs) => xs.reduce((a, b) => (b.r > a.r ? b : a));
  if (!G.trick.length) { const plain = ok.filter((c) => !isQS(c)); return low(plain.length ? plain : ok); }
  const led = G.trick[0][1].s;
  if (ok[0].s === led) {
    const top = Math.max(...G.trick.filter((t) => t[1].s === led).map((t) => t[1].r));
    const under = ok.filter((c) => c.r < top);
    if (under.length) return high(under);
    const pts = G.trick.reduce((n, t) => n + points(t[1]), 0);
    if (G.trick.length === 3 && pts === 0) { const safe = ok.filter((c) => !isQS(c)); return high(safe.length ? safe : ok); }
    return low(ok);
  }
  const qs = ok.find(isQS); if (qs) return qs;
  const hearts = ok.filter((c) => c.s === "H"); if (hearts.length) return high(hearts);
  return high(ok);
}

async function play(seat, card) {
  G.hands[seat] = G.hands[seat].filter((c) => !sameCard(c, card));
  G.broken = G.broken || card.s === "H";
  G.trick.push([seat, card]);
  if (G.trick.length < 4) return render();
  busy = true; // the trick is full: nobody plays until it's taken
  render();
  await wait(1100);
  const led = G.trick[0][1].s;
  const win = G.trick.filter((t) => t[1].s === led).reduce((a, b) => (b[1].r > a[1].r ? b : a))[0];
  const pts = G.trick.reduce((n, t) => n + points(t[1]), 0);
  G.taken[win].push(...G.trick.map((t) => t[1]));
  frame.log(`<b>${SEAT_NAME(win)}</b> take${win === YOU ? "" : "s"} the trick: ${G.trick.map((t) => said(t[1])).join(" ")}${pts ? ` · ${pts} point${pts > 1 ? "s" : ""}` : ""}`);
  G.trick = []; G.leader = win; G.tricks++;
  busy = false;
  if (G.tricks === 13) score();
  render();
}
async function run() {
  if (running) return;
  running = true; // the other seats are playing: your cards wait
  try {
    while (G.phase === "play" && toPlay() !== YOU) {
      await wait(520);
      await play(toPlay(), botCard(toPlay()));
    }
  } finally { running = false; }
  render();
}

function score() {
  let got = G.taken.map((t) => t.reduce((n, c) => n + points(c), 0));
  const moon = got.indexOf(26);
  if (moon >= 0) { got = got.map((_, i) => (i === moon ? 0 : 26)); frame.log(`<b>${SEAT_NAME(moon)} shot the moon!</b> Everyone else takes 26.`); }
  G.scores = G.scores.map((s, i) => s + got[i]);
  G.rows.push({ label: `${G.handNo + 1} · ${WAYS[G.way]}`, cells: got.map((g, i) => (moon === i ? "☾ 0" : g)) });
  G.over = Math.max(...G.scores) >= END;
  G.phase = G.over ? "over" : "between";
  if (G.over) { const best = Math.min(...G.scores); const w = G.scores.map((s, i) => (s === best ? SEAT_NAME(i) : null)).filter(Boolean); frame.log(`<b>Game over.</b> ${w.join(" and ")} win${w.length === 1 && w[0] !== "You" ? "s" : ""} on ${best}.`); }
}

/* ---------- drawing ---------- */
function render() {
  const turn = G.phase === "play" ? toPlay() : -1;
  const handPts = (i) => G.taken[i].reduce((n, c) => n + points(c), 0);
  for (const i of [0, 1, 3]) frame.seat(i, G.hands[i], { turn: turn === i, meta: `${G.scores[i]} · this hand ♥${handPts(i)}` });

  const at = (seat) => G.trick.find((t) => t[0] === seat);
  const slot = (seat, area) => `<div style="grid-area:${area};display:grid;place-items:center">${at(seat) ? cardHTML(at(seat)[1], { size: "" }) : ""}</div>`;
  if (G.phase === "pass") {
    const to = target(YOU, G.way);
    frame.middle(`<div class="count" style="font-size:.9rem">Passing <b style="color:var(--go)">${WAYS[G.way]}</b>, to ${SEAT_NAME(to)}<br>pick three, then pass</div>`);
  } else {
    frame.middle(`<div style="display:grid;grid-template-areas:'. n .' 'w . e' '. s .';grid-template-columns:repeat(3,auto);gap:4px">${slot(0, "n")}${slot(3, "w")}${slot(1, "e")}${slot(2, "s")}</div>`);
  }

  let can = () => false, chosen = (c) => G.chosen.some((x) => sameCard(x, c));
  if (G.phase === "pass") can = () => true;
  if (G.phase === "play" && turn === YOU && !busy && !running) { const ok = legal(G.hands[YOU], G.trick, G.broken, G.tricks === 0); can = (c) => ok.some((x) => sameCard(x, c)); }
  frame.mine(G.hands[YOU], { can, chosen, any: G.phase === "pass", turn: turn === YOU, locked: busy || running, meta:`${G.scores[YOU]} · this hand ♥${handPts(YOU)}` });

  if (G.phase === "pass") {
    frame.status(`Choose three cards to pass <b>${WAYS[G.way]}</b>.`);
    frame.actions(`<button class="btn" data-do="pass" ${G.chosen.length === 3 ? "" : "disabled"}>Pass ${G.chosen.length}/3 to ${SEAT_NAME(target(YOU, G.way))}</button>`);
  } else if (G.phase === "play") {
    const ok = turn === YOU ? legal(G.hands[YOU], G.trick, G.broken, G.tricks === 0) : [];
    const why = turn !== YOU ? "" : G.tricks === 0 && !G.trick.length ? "You hold the 2♣: it leads." : !G.trick.length && !G.broken && ok.every((c) => c.s !== "H") ? "Your lead. Hearts aren't broken yet." : G.trick.length && ok[0] && ok[0].s === G.trick[0][1].s ? `Follow ${SUIT_NAME[G.trick[0][1].s]}.` : "Your play.";
    const plain = G.trick.length ? "Your play." : "Your lead.";
    frame.status(turn === YOU ? `<b>${frame.hints ? why : plain}</b>` : `${SEAT_NAME(turn)} to play…`);
    frame.actions("");
  } else if (G.phase === "between") {
    frame.status(`Hand ${G.handNo + 1} is done.`);
    frame.actions(`<button class="btn" data-do="next">Deal hand ${G.handNo + 2}</button>`);
  } else {
    frame.status("<b>Game over.</b> The lowest score wins.");
    frame.actions(`<button class="btn" data-do="new">New game</button>`);
  }

  const best = Math.min(...G.scores);
  frame.score({ cols: SEATS.map((s, i) => SEAT_NAME(i)), rows: G.rows, totals: G.scores, lead: G.rows.length ? G.scores.map((s, i) => (s === best ? i : -1)) : [],
    note: "A point a heart, 13 for the Q♠. Take all 26 and everyone else takes 26 (☾). At 100 the game ends and the lowest total wins. Kept only while this page is open.", empty: "The first hand's points go here." });
  const inHands = G.hands.reduce((n, h) => n + h.length, 0), taken = G.taken.reduce((n, t) => n + t.length, 0);
  frame.deck([["In hands", inHands], ["Taken in tricks", taken], ["On the table", G.trick.length], ["Hearts broken", G.broken ? "yes" : "not yet"], ["Pass this hand", WAYS[G.way]], ["Tricks played", `${G.tricks} of 13`]],
    "52 cards, no jokers, 13 to a seat. The 2♣ leads the first trick.");
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.disabled) return;
  if (b.dataset.card) {
    const c = G.hands[YOU].find((x) => cardName(x) === b.dataset.card);
    if (G.phase === "pass") {
      const i = G.chosen.findIndex((x) => sameCard(x, c));
      if (i >= 0) G.chosen.splice(i, 1); else if (G.chosen.length < 3) G.chosen.push(c);
      return render();
    }
    if (G.phase === "play" && toPlay() === YOU && !busy && !running && G.trick.length < 4) {
      const ok = legal(G.hands[YOU], G.trick, G.broken, G.tricks === 0);
      if (!ok.some((x) => sameCard(x, c))) return frame.refuse(broken(c));
      play(YOU, c).then(run);
    }
    return;
  }
  const d = b.dataset.do;
  if (d === "pass") {
    const out = [0, 1, 2, 3].map((s) => (s === YOU ? G.chosen : botPass(G.hands[s])));
    out.forEach((cs, s) => { G.hands[s] = G.hands[s].filter((c) => !cs.some((x) => sameCard(x, c))); });
    out.forEach((cs, s) => G.hands[target(s, G.way)].push(...cs));
    G.hands.forEach(sortHand);
    const got = out[[0, 1, 2, 3].find((s) => target(s, G.way) === YOU)];
    frame.log(`You passed ${G.chosen.map(said).join(" ")} ${WAYS[G.way]}, and got ${got.map(said).join(" ")}.`);
    G.chosen = []; G.phase = "play"; lead(); render(); run();
  } else if (d === "next") { G.handNo++; deal(); }
  else if (d === "new") newGame();
});

frame.setup({ seats: true, score: true, deck: true, scoreTitle: "Scoresheet · points taken", redraw: render });
newGame();
