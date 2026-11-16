/* The Table: the box's stories played as game-master plays them
   (adapters/stdlib/game-master), in chapters that carry canon.

   An action beat rolls 2d6 and the acting character's stat, read strong (10+),
   weak (7-9) or miss (6-). A decision beat is a ruling: its fact waits for the
   game master's seal or decline, and only a seal makes it canon. An offer is
   what a seated character brings on the night, beside the story's path. A
   beat's `when` follows an earlier beat's result, a sealed offer, or a ruling
   sealed in an earlier chapter (story::scene::beat): the campaign this browser
   keeps is what those chapters made true.

   The binder is asked the way willow's own UI searches (ui/canvas.py): your
   words read through the GM's words list, ranked by pile-rank's BM25F, a page
   you named first, then what your words usually mean, then the ranking, each
   with why. It points at where to look; it doesn't answer for the binder. */

const WORLDS = GAME.worlds;
const PERSON = "you"; // the game master, at this browser

/* ---------- the campaign: what earlier chapters made true, kept in this browser ---------- */
const CAMPAIGN_KEY = "dn-campaign";
function loadCampaign() { try { const c = JSON.parse(localStorage.getItem(CAMPAIGN_KEY) || "null"); if (c && c.nights) return c; } catch (e) {} return { nights: [], sealed: {}, canon: [] }; }
function saveCampaign() { try { localStorage.setItem(CAMPAIGN_KEY, JSON.stringify(C)); } catch (e) {} }
let C = loadCampaign();

/* ---------- the story, as game-master plays it ---------- */
const TWO_D6 = [0, 0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1];
const BAND_LABEL = { strong: "Strong hit", weak: "Weak hit", miss: "Miss", sealed: "Sealed", declined: "Declined" };
const band = (t) => (t >= 10 ? "strong" : t >= 7 ? "weak" : "miss");
function odds(mod) { const o = { strong: 0, weak: 0, miss: 0 }; for (let t = 2; t <= 12; t++) o[band(t + mod)] += TWO_D6[t] / 36; return o; }

let S; // tonight
const world = () => WORLDS[S.w];
const char = (id) => world().characters.find((c) => c.id === id);
const statOf = (c, stat) => (c && c.stats && stat in c.stats ? c.stats[stat] : world().base_stat ?? 0);
const scene = () => world().scenes[S.scene];
const beatNow = () => { const sc = scene(); return sc ? sc.beats[S.beat] : null; };

function whenHolds(when) {
  if (!when) return true;
  if (when.beat) return when.is.includes(S.results[when.beat]);
  if (when.offered) return S.offers.some((o) => o.kind === when.offered && when.is.includes(o.status));
  if (when.sealed) return when.is.includes(C.sealed[when.sealed]); // an earlier chapter's ruling
  return false;
}
function nextBeat() {
  const w = world();
  while (S.scene < w.scenes.length) {
    const beats = w.scenes[S.scene].beats;
    while (++S.beat < beats.length) if (whenHolds(beats[S.beat].when)) return;
    S.scene++; S.beat = -1;
    if (S.scene < w.scenes.length) { S.opened = true; frame.log(`<b>${esc(w.scenes[S.scene].title)}</b>`); }
  }
}
function start(w) {
  S = { w, scene: 0, beat: -1, results: {}, offers: [], stat: null, roll: null, ruled: null, opened: true, committed: false, rolls: [] };
  frame.clearLog();
  frame.log(`<b>${esc(world().title)}</b> opens: ${esc(scene().title)}`);
  nextBeat();
  try { localStorage.setItem("dn-world", world().id); } catch (e) {}
  render();
}
function roll() {
  const b = beatNow(), c = char(b.by);
  const stat = S.stat || (frame.hints ? b.suggests : null);
  if (!stat) return frame.refuse("choose a stat to roll with.");
  const mod = statOf(c, stat), d = [1 + rnd(6), 1 + rnd(6)], total = d[0] + d[1] + mod, bd = band(total);
  S.roll = { d, mod, stat, total, band: bd };
  S.results[`${scene().id}::${b.id}`] = bd;
  S.rolls.push(bd);
  frame.log(`<b>${esc(c ? c.name : b.by)}</b> rolls ${esc(stat)}: ${d[0]}+${d[1]}${mod >= 0 ? "+" : "−"}${Math.abs(mod)} = ${total}, ${bd}`);
  render(true);
}
function rule(answer) {
  const b = beatNow();
  S.results[`${scene().id}::${b.id}`] = answer; S.ruled = answer;
  frame.log(answer === "sealed" ? `You sealed: ${esc(b.proposes.fact)}` : `You declined: ${esc(b.prompt)}`);
  render();
}
function advance() { S.roll = null; S.ruled = null; S.stat = null; S.opened = false; nextBeat(); render(); }
function tonightCanon() {
  const facts = [];
  for (const sc of world().scenes) for (const b of sc.beats)
    if (b.kind === "decision" && S.results[`${sc.id}::${b.id}`] === "sealed") facts.push({ fact: b.proposes.fact, key: `${world().id}::${sc.id}::${b.id}` });
  S.offers.forEach((o) => { if (o.status === "sealed") facts.push({ fact: o.fact, key: `${world().id}::offer::${o.kind}` }); });
  return facts;
}
/* the night ends: what it made true goes into the campaign, once */
function commit() {
  if (S.committed) return; S.committed = true;
  const w = world(), made = tonightCanon();
  for (const sc of w.scenes) for (const b of sc.beats) if (b.kind === "decision" && S.results[`${sc.id}::${b.id}`]) C.sealed[`${w.id}::${sc.id}::${b.id}`] = S.results[`${sc.id}::${b.id}`];
  made.forEach((m) => C.canon.push({ ...m, story: w.title }));
  C.nights.push({ story: w.id, title: w.title, date: new Date().toISOString().slice(0, 10), canon: made.length, rolls: S.rolls.length });
  saveCampaign();
  frame.log(`<b>The night ends.</b> ${made.length} fact${made.length === 1 ? "" : "s"} made canon, kept for the chapters after.`);
}

/* ---------- the binder, asked as willow's UI asks ---------- */
const FN = new Set(GAME.binder.function);
const ALIAS = GAME.binder.alias;
const wordsOf = (t) => t.normalize("NFC").toLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
function stem(w) { // the kernel's stem, rule for rule
  if (w.length < 3 || !/^[a-z]+$/.test(w)) return w;
  let s = w;
  if (s.length > 4 && (s.endsWith("ies") || s.endsWith("ied"))) s = s.slice(0, -3) + "y";
  else if (s.length > 4 && s.endsWith("ing")) s = s.slice(0, -3);
  else if (s.length > 3 && s.endsWith("ed") && !s.endsWith("eed")) s = s.slice(0, -2);
  else if (s.length > 3 && s.endsWith("s") && !s.endsWith("ss")) s = s.slice(0, -1);
  if (s.length > 3 && s[s.length - 1] === s[s.length - 2] && !"aeiouls".includes(s[s.length - 1])) s = s.slice(0, -1);
  if (s.length > 2 && s.endsWith("e")) s = s.slice(0, -1);
  return s;
}
const BREAK = /[.,;:!?()\[\]{}"|]/;
const lineTerms = (line) => wordsOf(line).filter((w) => !FN.has(w)).map(stem);
const clauses = (line) => line.split(BREAK).map(lineTerms).filter((ts) => ts.length);
const pairs = (ws) => ws.slice(1).map((b, i) => `${ws[i]} ${b}`);
const WEIGHT = { title: 2, asks: 1.5, body: 1 }, K1 = 1.2, BB = 0.75;
const RANK = (() => { // pile-rank's Ranker over the binder's passages
  const pile = GAME.binder.passages, first = new Map();
  pile.forEach((c, i) => { if (!first.has(c.id)) first.set(c.id, i); });
  const texts = [...first.values()].sort((a, b) => a - b), split = new Map();
  for (const i of texts) {
    const lines = pile[i].text.split("\n");
    split.set(i, {
      body: lines.flatMap(clauses),
      title: [lineTerms(pile[i].path), ...lines.filter((x) => x.trimStart().startsWith("#")).flatMap(clauses)],
      asks: lines.filter((x) => x.trimEnd().endsWith("?")).flatMap(clauses),
    });
  }
  const users = new Map();
  for (const f of split.values()) for (const p of new Set(f.body.flatMap(pairs))) users.set(p, (users.get(p) || 0) + 1);
  const phrases = new Set([...users].filter(([, n]) => n >= 2).map(([p]) => p));
  const counts = new Map(), length = new Map(), post = new Map();
  for (const [i, f] of split) {
    const per = {};
    for (const name of Object.keys(f)) { const got = new Map(); for (const ln of f[name]) for (const t of [...ln, ...pairs(ln).filter((p) => phrases.has(p))]) got.set(t, (got.get(t) || 0) + 1); per[name] = got; }
    counts.set(i, per);
    length.set(i, Object.fromEntries(Object.keys(f).map((n) => [n, f[n].reduce((a, ln) => a + ln.length, 0)])));
    for (const t of new Set(Object.values(per).flatMap((g) => [...g.keys()]))) { if (!post.has(t)) post.set(t, []); post.get(t).push(i); }
  }
  const n = Math.max(texts.length, 1), mean = {};
  for (const name of Object.keys(WEIGHT)) mean[name] = [...length.values()].reduce((a, x) => a + x[name], 0) / n;
  const terms = (q) => { const cs = clauses(q); return [...new Set([...cs.flat(), ...cs.flatMap(pairs).filter((p) => phrases.has(p))])]; };
  return (q, top) => {
    const ts = terms(q).filter((t) => post.has(t)), score = new Map();
    for (const t of ts) {
      const df = post.get(t).length, idf = Math.log((texts.length - df + 0.5) / (df + 0.5) + 1);
      for (const i of post.get(t)) {
        let tf = 0;
        for (const [name, w] of Object.entries(WEIGHT)) { const f = counts.get(i)[name].get(t) || 0; if (f) tf += (w * f) / (1 - BB + (BB * length.get(i)[name]) / (mean[name] || 1)); }
        score.set(i, (score.get(i) || 0) + (idf * tf * (K1 + 1)) / (tf + K1));
      }
    }
    return [...score.keys()].sort((a, b) => score.get(b) - score.get(a) || a - b).slice(0, top)
      .map((i) => ({ c: pile[i], score: score.get(i), held: ts.filter((t) => counts.get(i).body.has(t) || counts.get(i).title.has(t)) }));
  };
})();
function askBinder(question, top = 6) {
  const said = wordsOf(question);
  if (!said.length) return [];
  const asked = [...said, ...said.slice(1).map((b, i) => said[i] + b)]; // "spring wasps" is also "springwasps"
  const means = new Map();
  for (const w of asked) for (const m of ALIAS[w] || []) if (!means.has(m)) means.set(m, w);
  const ranked = RANK([...new Set([...asked, ...means.keys()])].join(" "), top * 2);
  const pageName = (path) => path.split("/").pop().replace(/\.[^.]+$/, "");
  const named = (path, ws) => { const nm = pageName(path); return [nm, ...nm.split("-")].find((p) => ws.includes(p) && p.length >= 3 && !FN.has(p)) || null; };
  const meanWords = [...means.keys()];
  const tier = (r) => (named(r.c.path, asked) ? 0 : named(r.c.path, meanWords) ? 1 : 2);
  return ranked.map((r, k) => ({ ...r, k })).sort((a, b) => tier(a) - tier(b) || a.k - b.k).slice(0, top).map((r) => {
    let why;
    if (named(r.c.path, asked)) why = "you named its page";
    else if (named(r.c.path, meanWords)) why = `what “${means.get(named(r.c.path, meanWords))}” usually means here`;
    else { // the words it holds, as you said them, not their plain forms
      const yours = (t) => [...asked, ...meanWords].find((w) => stem(w) === t || w === t) || t;
      why = r.held.length ? `holds ${[...new Set(r.held.slice(0, 4).map(yours))].join(", ")}` : "close to what you said";
    }
    return { ...r, why };
  });
}

/* ---------- between sessions: ideas.py's four parts, for the GM's eyes ----------
   Nothing here is canon and nothing is handed in: an idea the GM likes, they
   write in the binder or into a story. */
const FILES = GAME.binder.files;
const NOTES = ["sessions", "scanned"];
const utcDay = () => new Date().toISOString().slice(0, 10);
function titled(folder) { // each page's first heading, the name it was written under
  return Object.keys(FILES).filter((p) => p.startsWith(folder + "/") && !p.slice(folder.length + 1).includes("/") && p.endsWith(".md")).sort()
    .map((p) => { const ln = FILES[p].split(/\r?\n/).find((l) => l.startsWith("# ")); return ln ? ln.slice(2).trim() : ""; }).filter(Boolean);
}
function saidInNotes() { return Object.keys(FILES).filter((p) => NOTES.some((n) => p.startsWith(n + "/") && !p.slice(n.length + 1).includes("/"))).sort().map((p) => FILES[p].toLowerCase()).join("\n"); }
function unplayed() {
  const said = saidInNotes(), out = [];
  for (const folder of ["monsters", "people"]) for (const name of titled(folder)) {
    const ws = (name.toLowerCase().match(/[a-z']+/g) || []).filter((w) => !["the", "a", "an"].includes(w));
    if (ws.length && !ws.every((w) => new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(said))) out.push({ name, folder });
  }
  return out;
}
function promised() { // every line of the GM's notes that says next time, oldest file first
  const out = [];
  for (const p of Object.keys(FILES).sort()) FILES[p].split(/\r?\n/).forEach((t, i) => { if (t.toLowerCase().includes("next time")) out.push({ path: p, line: i + 1, text: t.trim() }); });
  return out;
}
const lowerFirst = (t) => (t.slice(0, 1) !== t.slice(0, 1).toLowerCase() && t.slice(1, 2) === t.slice(1, 2).toLowerCase() ? t.slice(0, 1).toLowerCase() + t.slice(1) : t);
const uniqSorted = (xs) => [...new Set(xs)].sort();
function ideaWorlds(only) {
  if (only) return WORLDS.filter((w) => only.includes(w.id));
  const last = C.nights.length ? C.nights[C.nights.length - 1].story : null;
  const w = WORLDS.find((x) => x.id === last);
  return w ? [w] : WORLDS;
}
function ideaGrammar(worlds, canonFacts) { // a Tracery grammar of the box's own words
  const who = [], npc0 = [], places = [];
  for (const w of worlds) { for (const c of w.characters) (c.seat ? who : npc0).push(c.name); places.push(...w.places.map((p) => p.name)); }
  let npc = [...npc0, ...titled("people").filter((n) => !npc0.includes(n))].map((n) => (n.startsWith("The ") ? "the " + n.slice(4) : n));
  const monster = titled("monsters").map((n) => `the ${n.toLowerCase()}`);
  const thread = [];
  for (const { text } of promised()) { const m = /next time:?\s*(.+)/i.exec(text); if (m && m[1].split(/\s+/).filter(Boolean).length > 2) thread.push(m[1].replace(/[.!?]+$/, "")); }
  const canon = canonFacts.map((f) => lowerFirst(f.split("  [offered by")[0].split(":")[0].replace(/\.+$/, "")));
  const g = {};
  const put = (k, v) => { if (v.length) g[k] = v; };
  put("who", uniqSorted(who)); put("npc", uniqSorted(npc)); put("place", uniqSorted(places.map((p) => p.toLowerCase())));
  put("monster", monster); put("thread", thread); put("canon", canon);
  const has = (...ks) => ks.every((k) => k in g), origin = [];
  if (has("who", "thread")) origin.push("What if #who# finds out #thread#, and doesn't tell the others?");
  if (has("monster", "place", "who")) origin.push("At #place#, #who# comes face to face with #monster#.");
  if (has("npc", "who", "thread")) origin.push("#npc.capitalize# asks #who# for help with #thread#.");
  if (has("canon", "npc")) origin.push("Because #canon#, #npc# owes someone at the table a favour.");
  if (has("canon", "monster")) origin.push("Now that #canon#, #monster# has nowhere to go.");
  if (has("who", "npc")) origin.push("#who.capitalize# and #npc# want the same thing, for different reasons.");
  g.origin = origin;
  return g;
}
const LABEL = utf8("willow surprise");
const daySeed = (day) => hex(sha256(utf8("willow surprise " + day)));
function surprise(seedHex) { // random-passage's draw: one passage of eight words or more
  const long = GAME.binder.passages.filter((c) => wordsOf(c.text).length >= 8);
  if (!long.length) return null;
  const seed = new Uint8Array(seedHex.match(/../g).map((h) => parseInt(h, 16)));
  const both = new Uint8Array(seed.length + LABEL.length); both.set(seed); both.set(LABEL, seed.length);
  return long[new Stream(both).below(long.length)];
}
function ideas(seed, count, only) {
  const worlds = ideaWorlds(only), g = ideaGrammar(worlds, only ? [] : C.canon.map((c) => c.fact));
  const seeds = g.origin.length ? Array.from({ length: count }, (_, i) => oracleReading(g, seed, i + 1)) : [];
  return { worlds, seeds, unplayed: unplayed(), promised: promised() };
}
window.__ideas = (seed, count, only, surpriseSeed) => { const r = ideas(seed, count, only); const c = surprise(surpriseSeed); return { seeds: r.seeds, unplayed: r.unplayed, promised: r.promised, surprise: c && `${c.path}:${c.line}` }; };

let mode = "table";
const B = { seed: `ideas ${utcDay()}`, count: 5, surpriseSeed: daySeed(utcDay()) };
function betweenHTML() {
  let r, err = "";
  try { r = ideas(B.seed, B.count); } catch (e) { err = e.message; r = { worlds: ideaWorlds(), seeds: [], unplayed: unplayed(), promised: promised() }; }
  const c = surprise(B.surpriseSeed);
  const forWhat = r.worlds.length === 1 ? `for ${esc(r.worlds[0].title)}, the story last played` : "from every story in the box, since none has been played here yet";
  const sec = (title, body) => `<section style="display:grid;gap:8px;width:min(640px,100%)"><h3 style="margin:0;font-family:var(--lid-font);font-weight:400;font-size:1.15rem">${title}</h3>${body}</section>`;
  return `<p class="note" style="text-align:center;margin:0;max-width:60ch">For the GM's eyes. Nothing here is canon and nothing is handed in: an idea you like, you write in the binder or into a story.</p>
    ${sec("Seeds", `<form id="seeds-form" class="actions" style="justify-content:flex-start;gap:6px" autocomplete="off"><label class="count" for="seeds-seed">Seed</label><input id="seeds-seed" value="${esc(B.seed)}" spellcheck="false" style="font:inherit;font-family:var(--mono);width:19ch;padding:6px 9px;border-radius:8px;border:1px solid var(--edge);background:#0004;color:var(--chalk)"><label class="count" for="seeds-count">How many</label><input id="seeds-count" type="number" min="1" max="20" value="${B.count}" style="font:inherit;width:5ch;padding:6px;border-radius:8px;border:1px solid var(--edge);background:#0004;color:var(--chalk)"><button class="btn" type="submit">Deal</button><button class="btn ghost" type="button" data-act="seeds-fresh">Another seed</button></form>
      <p class="note" style="margin:0">Dealt ${forWhat}, from its people and places, the binder's monsters and people, the threads promised for next time${C.canon.length ? ", and what the table made true" : ""}. The same seed deals them again.</p>
      ${err ? `<p style="color:#ff9b85;margin:0">${esc(err)}</p>` : r.seeds.length ? `<ul style="margin:0;padding-left:18px;display:grid;gap:6px;font-family:var(--prose);font-size:1.05rem">${r.seeds.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="note">The box has too little in it yet to deal from.</p>`}`)}
    ${sec("Set up, never played", r.unplayed.length ? `<ul style="margin:0;padding-left:18px">${r.unplayed.map((u) => `<li>${esc(u.name)} <span class="note">(${esc(u.folder)}/)</span></li>`).join("")}</ul><p class="note" style="margin:0">A monster or person with a page in the binder whose name no session's notes have said yet.</p>` : `<p class="note">Everything the binder sets up has come out at the table.</p>`)}
    ${sec("Still open", r.promised.length ? `<ul style="margin:0;padding-left:18px;display:grid;gap:4px">${r.promised.map((p) => `<li><span style="font-family:var(--mono);font-size:.78rem;color:var(--chalk-dim)">${esc(p.path)}:${p.line}</span> ${esc(p.text)}</li>`).join("")}</ul>` : `<p class="note">No promises made for next time.</p>`)}
    ${sec("Something you wrote and forgot", c ? `<p class="count" style="text-align:left;margin:0">From ${esc(c.path)}, line ${c.line}:</p><blockquote style="margin:0;padding:8px 14px;border-left:3px solid var(--edge);font-family:var(--prose);white-space:pre-wrap">${esc(c.text)}</blockquote><div class="actions" style="justify-content:flex-start"><button class="btn ghost" data-act="surprise">Draw another</button><span class="note" style="font-family:var(--mono);font-size:.68rem;word-break:break-all">seed ${B.surpriseSeed.slice(0, 16)}… ${B.surpriseSeed === daySeed(utcDay()) ? "(today's: the same passage all day)" : ""}</span></div>` : `<p class="note">Nothing in the binder is long enough to draw.</p>`)}`;
}

/* ---------- drawing ---------- */
const modeSwitch = () => `<div class="actions" style="gap:6px" role="group" aria-label="Which side of the screen">${[["table", "At the table"], ["between", "Between sessions"]].map(([m, l]) => `<button class="toggle" data-mode="${m}" aria-pressed="${mode === m}">${l}</button>`).join("")}</div>`;
function stageHTML(tumble) {
  if (mode === "between") return modeSwitch() + betweenHTML();
  const w = world();
  const chips = WORLDS.map((x, i) => {
    const played = C.nights.filter((n) => n.story === x.id).length;
    return `<button class="toggle" style="border-color:var(--edge)" data-w="${i}" aria-pressed="${i === S.w}">${esc(x.title)}${played ? ` ✓${played > 1 ? played : ""}` : ""}</button>`;
  }).join("");
  const head = `${modeSwitch()}<div class="actions" style="gap:6px">${chips}</div><p class="note" style="font-style:italic;max-width:62ch;text-align:center;margin:0">${esc(w.setting)}</p>`;
  const sc = scene();
  if (!sc) {
    const n = (k) => S.rolls.filter((r) => r === k).length, made = tonightCanon();
    return `${head}<div style="display:grid;gap:10px;justify-items:center;text-align:center;padding:12px 0">
      <span class="count">the night ends</span><h2 style="font-family:var(--lid-font);font-weight:400;font-size:2rem;margin:0">${esc(w.title)}</h2>
      <p style="margin:0">${S.rolls.length} roll${S.rolls.length === 1 ? "" : "s"}: ${n("strong")} strong, ${n("weak")} weak, ${n("miss")} miss. ${made.length} fact${made.length === 1 ? "" : "s"} made canon, kept for the next chapter.</p>
      <div class="actions"><button class="btn" data-act="restart">Play it again</button></div></div>`;
  }
  const place = (w.places.find((p) => p.id === sc.place) || {}).name || "";
  let card = "";
  const b = beatNow();
  if (b.kind === "action") {
    const c = char(b.by), chosen = S.roll ? S.roll.stat : S.stat || (frame.hints ? b.suggests : null);
    const stats = w.stats.map((st) => {
      const m = statOf(c, st), o = odds(m), pct = (x) => Math.round(x * 100);
      return `<button class="toggle" data-stat="${esc(st)}" aria-pressed="${st === chosen}" ${S.roll ? "disabled" : ""} style="display:grid;gap:4px;min-width:110px;text-align:left;border-color:var(--edge);border-radius:10px;padding:8px 10px">
        <span style="display:flex;justify-content:space-between;gap:8px"><b>${esc(st)}</b><span style="font-family:var(--mono)">${m >= 0 ? "+" : "−"}${Math.abs(m)}</span></span>
        ${frame.hints ? `<span style="display:flex;height:5px;border-radius:3px;overflow:hidden"><i style="width:${pct(o.strong)}%;background:#6fc3a0"></i><i style="width:${pct(o.weak)}%;background:#e2b04f"></i><i style="width:${pct(o.miss)}%;background:#e0745e"></i></span><span class="count" style="text-align:left">${pct(o.strong)}% strong${st === b.suggests ? " · suggested" : ""}</span>` : ""}
      </button>`;
    }).join("");
    const r = S.roll;
    card = `<span class="count">${esc(c ? c.name : b.by)}${c && c.role ? `, ${esc(c.role)}` : ""} · action</span>
      <p style="font-family:var(--prose);font-size:1.3rem;margin:0;text-align:center;max-width:40ch">${esc(b.prompt)}</p>
      <div class="actions" style="gap:8px" role="group" aria-label="Roll with which stat">${stats}</div>
      <div class="dice-row">${r ? dieHTML(r.d[0], { roll: tumble }) + dieHTML(r.d[1], { roll: tumble }) + `<span class="count" style="font-size:.95rem">+ ${r.mod} ${esc(r.stat)} = <b style="font-size:1.4rem;color:var(--chalk)">${r.total}</b></span>` : `<button class="btn" data-act="roll">${chosen ? `Roll 2d6 + ${esc(chosen)}` : "Choose a stat, then roll"}</button>`}</div>
      ${r ? `<div style="border-left:3px solid ${{ strong: "#6fc3a0", weak: "#e2b04f", miss: "#e0745e" }[r.band]};padding:2px 0 2px 12px;max-width:44ch"><span class="count">${BAND_LABEL[r.band]}</span><p style="margin:2px 0 0;font-family:var(--prose);font-size:1.1rem">${esc(b.outcomes[r.band])}</p></div><button class="btn" data-act="next">Next beat</button>` : ""}`;
  } else {
    const p = b.proposes, by = char(p.proposed_by);
    card = `<span class="count">a ruling</span>
      <p style="font-family:var(--prose);font-size:1.3rem;margin:0;text-align:center;max-width:40ch">${esc(b.prompt)}</p>
      <blockquote style="margin:0;padding:12px 16px;border:2px dashed #9db8f0;border-radius:10px;font-family:var(--prose);font-size:1.08rem;max-width:44ch">${esc(p.fact)}<div class="count" style="text-align:left;margin-top:4px">proposed by ${esc(by ? by.name : p.proposed_by)}</div></blockquote>
      ${S.ruled ? `<p style="margin:0">${S.ruled === "sealed" ? "<b>Sealed.</b> It is canon now." : "<b>Declined.</b> The story goes on without it."}</p><button class="btn" data-act="next">Next beat</button>`
        : `<div class="actions"><button class="btn" data-act="seal" style="background:#9db8f0;color:#101a33">Seal it</button><button class="btn ghost" data-act="decline">Decline</button></div><p class="note" style="margin:0">You're the game master: the call is yours; the table only proposes.</p>`}`;
  }
  return `${head}
    <div style="display:grid;gap:4px;justify-items:center;text-align:center">
      <span class="count">scene ${S.scene + 1} of ${w.scenes.length} · ${esc(place)}</span>
      <h2 style="font-family:var(--lid-font);font-weight:400;font-size:clamp(1.5rem,3.4vw,2.1rem);margin:0">${esc(sc.title)}</h2>
      ${S.opened && sc.opening ? sc.opening.map((l) => `<p style="margin:0;font-family:var(--prose)">${esc(l)}</p>`).join("") : ""}
    </div>
    <div style="display:grid;gap:12px;justify-items:center;padding:6px 0 4px">${card}</div>`;
}

function render(tumble) {
  if (!scene() && !S.committed) commit();
  frame.stage(stageHTML(tumble));
  frame.status(""); frame.actions("");
  const w = world();
  frame.panel("cast", "At the table", w.characters.map((c) => `<div style="display:grid;gap:3px;${c.seat ? "" : "opacity:.7"}">
    <div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(c.name)}</b><span class="note">${esc(c.role || "")}${c.seat ? "" : " · not a seat"}</span></div>
    ${c.seat ? `<div style="display:flex;flex-wrap:wrap;gap:4px">${w.stats.map((st) => { const m = statOf(c, st); return `<span style="font-family:var(--mono);font-size:.7rem;padding:1px 6px;border-radius:5px;border:1px solid var(--edge);${m > (w.base_stat ?? 0) ? "color:var(--go)" : "color:var(--chalk-dim)"}">${esc(st)} ${m >= 0 ? "+" : "−"}${Math.abs(m)}</span>`; }).join("")}</div>` : ""}</div>`).join(""));
  const tonight = tonightCanon(), before = C.canon;
  frame.panel("canon", "Canon", (tonight.length || before.length)
    ? `${tonight.map((f) => `<p style="margin:0;padding-left:10px;border-left:2px solid #9db8f0">${esc(f.fact)}</p>`).join("")}
       ${before.length ? `<p class="note" style="margin:6px 0 0">From earlier chapters:</p>${before.slice().reverse().map((f) => `<p style="margin:0;padding-left:10px;border-left:2px solid var(--edge);color:var(--chalk-dim)">${esc(f.fact)} <span class="note">· ${esc(f.story)}</span></p>`).join("")}` : ""}`
    : `<p class="note">Nothing yet. A fact becomes canon only when you seal it.</p>`);
  const kinds = w.offers && w.offers.length ? w.offers : ["fact"];
  frame.panel("offers", "Offers");
  if (!$("offer-form")) $("offers").innerHTML = `<div id="offer-list"></div><form id="offer-form" style="display:grid;gap:6px">
      <select id="offer-by" aria-label="Who brings it"></select><select id="offer-kind" aria-label="What kind"></select>
      <textarea id="offer-fact" rows="2" placeholder="A guest walks in, carrying their own light…" style="font:inherit;font-family:var(--prose);padding:8px;border-radius:8px;border:1px solid var(--edge);background:#0004;color:var(--chalk)"></textarea>
      <button class="btn ghost" type="submit">Bring it to the table</button><p class="note">An offer waits beside the story; the beats go on while it does.</p></form>`;
  const by = $("offer-by"), kind = $("offer-kind");
  const seatOpts = w.characters.filter((c) => c.seat).map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
  if (by.dataset.w !== String(S.w)) { by.innerHTML = seatOpts; kind.innerHTML = kinds.map((k) => `<option>${esc(k)}</option>`).join(""); by.dataset.w = String(S.w); }
  $("offer-list").innerHTML = S.offers.map((o, i) => `<div style="display:grid;gap:4px;padding:8px;border:1px dashed var(--edge);border-radius:8px;margin-bottom:6px"><span class="count" style="text-align:left">${esc(char(o.by).name)} · ${esc(o.kind)} · ${esc(o.status)}</span><span>${esc(o.fact)}</span>${o.status === "waiting" ? `<div class="actions" style="justify-content:flex-start"><button class="btn" style="padding:4px 10px;background:#9db8f0;color:#101a33" data-offer="${i}" data-ans="sealed">Seal</button><button class="btn ghost" style="padding:4px 10px" data-offer="${i}" data-ans="declined">Decline</button></div>` : ""}</div>`).join("");
  frame.panel("campaign", "The campaign", `${C.nights.length ? C.nights.slice().reverse().slice(0, 8).map((n) => `<div class="deck-row"><span>${esc(n.title)}</span><span>${n.date} · ${n.canon} canon</span></div>`).join("") : `<p class="note">No nights yet. When a story ends, what it made true is kept here, and later chapters can turn on it.</p>`}
    ${C.nights.length ? (S.confirmReset ? `<div class="actions" style="justify-content:flex-start"><span class="note">Forget every night and its canon?</span><button class="btn" style="padding:4px 10px" data-act="reset-yes">Forget it all</button><button class="btn ghost" style="padding:4px 10px" data-act="reset-no">Keep it</button></div>` : `<button class="btn ghost" style="padding:4px 10px;justify-self:start" data-act="reset">Start a new campaign</button>`) : ""}
    <p class="note">Kept in this browser only. The campaign that counts is the record's.</p>`);
}

function renderBinder(question) {
  const found = askBinder(question);
  $("binder-results").innerHTML = !question.trim() ? "" : found.length
    ? found.map((r) => `<details style="border-top:1px solid var(--edge);padding:6px 0"><summary style="cursor:pointer"><b>${esc(r.c.path)}:${r.c.line}</b> <span class="note">· ${esc(r.why)}</span></summary><p style="margin:6px 0 0;white-space:pre-wrap;font-family:var(--prose);font-size:.9rem">${esc(r.c.text)}</p></details>`).join("") + `<p class="note">Where to look, in order: pages you named, then what your words usually mean, then the ranking. It points; it doesn't answer for the binder.</p>`
    : `<p class="note">Nothing in the binder holds those words. A word you use that the binder doesn't is a line for gm-words.txt.</p>`;
}

/* ---------- events ---------- */
document.addEventListener("click", (e) => {
  const t = e.target.closest("button"); if (!t || t.disabled) return;
  if (t.dataset.mode) { mode = t.dataset.mode; return render(); }
  if (t.dataset.w) return start(+t.dataset.w);
  if (t.dataset.stat) { S.stat = t.dataset.stat; return render(); }
  if (t.dataset.offer) { const o = S.offers[+t.dataset.offer]; o.status = t.dataset.ans; frame.log(`${o.status === "sealed" ? "Canon" : "Set aside"}: ${esc(o.fact)}`); return render(); }
  const a = t.dataset.act;
  if (a === "roll") roll();
  else if (a === "next") advance();
  else if (a === "seal") rule("sealed");
  else if (a === "decline") rule("declined");
  else if (a === "restart") start(S.w);
  else if (a === "seeds-fresh") { B.seed = seedWords(); render(); }
  else if (a === "surprise") { B.surpriseSeed = hex(crypto.getRandomValues(new Uint8Array(32))); render(); }
  else if (a === "reset") { S.confirmReset = true; render(); }
  else if (a === "reset-no") { S.confirmReset = false; render(); }
  else if (a === "reset-yes") { C = { nights: [], sealed: {}, canon: [] }; saveCampaign(); S.confirmReset = false; frame.log("<b>A new campaign.</b> Every earlier night is forgotten here."); render(); }
});
document.addEventListener("submit", (e) => {
  if (e.target.id === "offer-form") {
    e.preventDefault();
    const fact = $("offer-fact").value.trim(); if (!fact) return $("offer-fact").focus();
    S.offers.push({ by: $("offer-by").value, kind: $("offer-kind").value, fact, status: "waiting" });
    frame.log(`<b>${esc(char($("offer-by").value).name)}</b> offers: ${esc(fact)}`);
    $("offer-fact").value = ""; render();
  } else if (e.target.id === "seeds-form") {
    e.preventDefault(); B.seed = $("seeds-seed").value.trim() || B.seed; B.count = Math.max(1, Math.min(20, +$("seeds-count").value || 5)); render();
  } else if (e.target.id === "binder-form") { e.preventDefault(); renderBinder($("binder-q").value); }
});

window.__rank = RANK; window.__ask = askBinder; // for checking against willow
frame.setup({ seats: false, score: false, deck: false, redraw: () => render() });
frame.panel("binder", "Ask the binder", `<form id="binder-form" style="display:flex;gap:6px"><input id="binder-q" placeholder="what are the hound's stats" aria-label="Ask the binder" style="flex:1;min-width:0;font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--edge);background:#0004;color:var(--chalk)"><button class="btn" type="submit">Ask</button></form><div id="binder-results" style="display:grid;gap:2px"></div>`);
let first = Math.max(0, WORLDS.findIndex((w) => w.id === "lantern-fair"));
try { const id = localStorage.getItem("dn-world"); const i = WORLDS.findIndex((w) => w.id === id); if (i >= 0) first = i; } catch (e) {}
start(first);
