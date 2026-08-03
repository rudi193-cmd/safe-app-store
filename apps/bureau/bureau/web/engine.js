/* bureau — browser engine. Logic only.
 *
 * Every office, document, rule and line of prose is GENERATED from graph.py by
 * bureau/web/build.py and injected as BUREAU_DATA. There is no hand-copy here,
 * which is what closes the hole the previous version documented: prose can no
 * longer drift between the two engines, because only one of them has any.
 *
 * The mechanics below are mirrored from bureau/{rng,napkin,play}.py and held to
 * it by tests/test_differential.py. Loaded as a plain script in the page and as
 * CJS under node. No DOM in here.
 */
"use strict";

var DATA = typeof BUREAU_DATA !== "undefined" ? BUREAU_DATA : null;

/* ── rng: xorshift32, mirroring bureau/rng.py ───────────────────────────────── */
function Rng(seed) {
  var s = (Math.imul(seed, 2654435761) + 1) >>> 0;
  this._s = s === 0 ? 0x9e3779b9 : s;
}
Rng.prototype.u32 = function () {
  var x = this._s;
  x = (x ^ (x << 13)) >>> 0;
  x = (x ^ (x >>> 17)) >>> 0;
  x = (x ^ (x << 5)) >>> 0;
  this._s = x;
  return x;
};
Rng.prototype.below = function (n) { return this.u32() % n; };
Rng.prototype.between = function (lo, hi) { return lo + this.below(hi - lo); };
Rng.prototype.pick = function (seq) { return seq[this.below(seq.length)]; };

/* ── requirement matching, mirroring graph.Req ──────────────────────────────── */
function metBy(req, docId, credulous) {
  var doc = DATA.docs[docId];
  if (!doc || doc.kind !== req.kind) return false;
  if (credulous) return true;
  return req.needs.every(function (n) { return doc.qual.indexOf(n) >= 0; });
}
function satisfied(req, held, credulous) {
  for (var d of held) if (metBy(req, d, credulous)) return true;
  return false;
}
function canServe(office, held) {
  return office.requires.every(function (r) { return satisfied(r, held, false); });
}
function describeReq(r) {
  return r.needs.length ? r.kind + " (" + r.needs.slice().sort().join("/") + ")" : r.kind;
}
function refusalTier(office, visits) {
  if (!office.on_refuse.length) return 0;
  return Math.min(Math.max(visits - 1, 0), office.on_refuse.length - 1);
}

/* ── session ────────────────────────────────────────────────────────────────── */
var NAPKIN_WORD = "napkin_word";
var NAPKIN_BLANK = "napkin_blank";
var FACES = ["word", "word", "word", "blank", "blank", "grape"];

function Session(seed) {
  this.rng = new Rng(seed >>> 0);
  this.surprise = DATA.starting_surprise;
  this.dwell = 0;
  this.threshold = this.rng.between(3, 9);
  this.held = new Set();
  this.seen = new Set();
  this.visits = {};
  this.lastTier = 0;
  this.resolution = null;
}

Session.prototype.gooVisible = function () { return this.surprise <= 0; };

Session.prototype._tick = function () {
  if (!this.gooVisible()) return null;
  this.dwell += 1;
  if (this.dwell < this.threshold) return null;
  var face = this.rng.pick(FACES);
  if (face === "grape") {
    this.dwell = 0;
    this.threshold = this.rng.between(3, 9);
  }
  if (face === "word") this.held.add(NAPKIN_WORD);
  if (face === "blank") this.held.add(NAPKIN_BLANK);
  return face;
};

Session.prototype.visit = function (officeId) {
  var office = DATA.offices[officeId];
  if (!office) return { lines: [{ kind: "sys", text: "There is no such office. There is a rumour of one." }] };
  if (this.resolution) return { lines: [{ kind: "sys", text: "The matter is closed. You keep going anyway, out of habit." }] };

  var lines = [{ kind: "head", text: office.name, sub: office.staff }];
  var firstTime = !this.seen.has(office.id);
  this.seen.add(office.id);
  this.visits[office.id] = (this.visits[office.id] || 0) + 1;

  var spent = this.surprise > 0;
  if (spent) this.surprise -= 1;
  if (firstTime) lines.push({ kind: "rule", text: office.rule });
  if (spent && this.surprise === 0) {
    lines.push({ kind: "goo", text: DATA.goo_line });
  }

  if (!canServe(office, this.held)) {
    this.lastTier = refusalTier(office, this.visits[office.id]);
    lines.push({ kind: "refuse", text: office.on_refuse.length ? office.on_refuse[this.lastTier] : office.rule });
    var self = this;
    var gaps = office.requires.filter(function (r) { return !satisfied(r, self.held, false); });
    lines.push({ kind: "missing", text: gaps.map(describeReq).join(", "), reqs: gaps });
  } else if (office.issues) {
    if (office.consumes_ticket) this.held.delete("ticket");
    this.held.add(office.issues);
    lines.push({ kind: "issue", text: office.on_issue });
  } else {
    this.lastTier = refusalTier(office, this.visits[office.id]);
    lines.push({ kind: "refuse", text: office.on_refuse.length ? office.on_refuse[this.lastTier] : office.rule });
  }

  var face = this._tick();
  if (face) {
    lines.push({ kind: "gerald", text: "Gerald appears." });
    lines.push({ kind: "declare", text: DATA.declaration[face], face: face });
    if (face === "word") lines.push({ kind: "note", text: "you take the napkin. Hanz can read what he writes." });
    if (face === "blank") lines.push({ kind: "note", text: "you take the napkin. It is blank. It is not nothing." });
  }
  return { lines: lines };
};

Session.prototype.hand = function (officeId) {
  if (officeId === "hanz" && this.held.has(NAPKIN_WORD)) {
    this.resolution = "enrolled";
    return { lines: [{ kind: "ending", text: "enrolled" }] };
  }
  if (officeId === "records" && this.held.has(NAPKIN_BLANK)) {
    this.resolution = "voided";
    return { lines: [{ kind: "ending", text: "voided" }] };
  }
  if (this.held.has(NAPKIN_WORD) || this.held.has(NAPKIN_BLANK)) {
    return { lines: [{ kind: "sys", text: "They look at the napkin. They are not the one who can read it." }] };
  }
  return { lines: [{ kind: "sys", text: "You have nothing to hand over that anyone here is able to receive." }] };
};

Session.prototype.state = function () {
  return {
    held: Array.from(this.held).sort(),
    surprise: this.surprise,
    dwell: this.dwell,
    tier: this.lastTier,
    resolution: this.resolution,
  };
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    Rng: Rng,
    Session: Session,
    setData: function (d) { DATA = d; },
  };
}
