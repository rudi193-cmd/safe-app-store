#!/usr/bin/env node
/**
 * jarvis's ranker, answering Nestor's stage-3 probe list.
 *
 * Two independent implementations, one corpus, one probe list. Nestor's
 * `bench/bench_surfaces_human.py` measured document-alias retrieval with three
 * matchers — character difflib, token Jaccard, token containment — on verbatim
 * spans of one person's prose. jarvis's `memory.search` is a fourth: IDF-weighted
 * token overlap, with subject and alias hits weighted 2.5x body hits.
 *
 * It was written for a different reason (a phone assistant's fact store) and
 * has never been measured against anything real, which is the second thing this
 * closes.
 *
 * WHAT IS jarvis's CODE AND WHAT IS NOT — the honest boundary
 * ----------------------------------------------------------
 * Imported unmodified from `../src/text.js`: `tokenize`, `tokensFor`, and the
 * stemmer and stopword list underneath them. Tokenization is the half most
 * likely to differ between implementations, so it is the half that must not be
 * re-expressed.
 *
 * Re-expressed here: the scoring loop of `Memory.search`, over a plain Map
 * instead of IndexedDB. The formula is copied line for line —
 *
 *     const idf = Math.log(1 + total / df);
 *     entry.score += idf * (strong ? 2.5 : 1);
 *
 * — as is the sort, including the `createdAt` recency tiebreak, which is
 * load-bearing: a test in `suite.js` was once passing on the tiebreak while
 * claiming to be about relevance. `df` here is a count over the fact set, which
 * is what `index.count(token)` returns; `total` is the live fact count.
 *
 * NOT re-expressed, and it does not apply: the storage layer, the `live`/
 * `supersedes` retirement machinery, and the schema migration. Every fact in
 * this corpus is live and nothing supersedes anything.
 *
 * Mapping onto jarvis's model
 * ---------------------------
 *     referent  -> one fact
 *     canonical -> `subject`
 *     surfaces  -> `aliases`
 *     (no body) -> `text` is empty
 *
 * So every token is a *strong* token. That is the correct mapping — a sealed
 * surface is a deliberate handle, which is exactly what jarvis's 2.5x weight is
 * for — and it also means the 2.5x weight cannot differentiate anything here,
 * so this run does not test it.
 *
 * jarvis has no threshold. Scores are unbounded IDF sums, not similarities in
 * [0,1], so recall@0.92 is not a question that can be asked of it — only
 * rank@1. Which is the point: stage 3 concluded that ranking is what survives
 * on real prose, and jarvis was already built as a ranker.
 *
 * Usage:
 *   node jarvis/test/terpsi-rank.js <path to terpsi_splits.json>
 */
import { readFileSync } from 'node:fs';
import { tokenize, tokensFor } from '../src/text.js';

function buildFacts(canonical, sealed) {
  return Object.entries(sealed).map(([ref, surfaces], i) => {
    const { strong, all } = tokensFor({
      subject: canonical[ref],
      aliases: surfaces,
      text: '',
    });
    return { id: ref, subject: canonical[ref], strongTokens: strong,
             tokens: all, createdAt: i };
  });
}

/** The scoring loop of Memory.search, over a Map instead of an object store. */
function search(facts, query) {
  const queryTokens = tokenize(query);
  if (!queryTokens.length) return [];

  const total = facts.length;
  if (!total) return [];

  const hits = new Map();
  for (const token of queryTokens) {
    const matches = facts.filter((f) => f.tokens.includes(token));
    const df = matches.length;
    if (!df) continue;
    const idf = Math.log(1 + total / df);
    for (const fact of matches) {
      const entry = hits.get(fact.id) || { fact, score: 0, matched: [] };
      const strong = (fact.strongTokens || []).includes(token);
      entry.score += idf * (strong ? 2.5 : 1);
      entry.matched.push(token);
      hits.set(fact.id, entry);
    }
  }
  return [...hits.values()]
    .map((h) => (NORMALIZE
      ? { ...h, score: h.score / factNorm(h.fact) }
      : h))
    .sort((a, b) => b.score - a.score || b.fact.createdAt - a.fact.createdAt);
}

/**
 * Length normalization is now what jarvis ships, and this measurement is why.
 *
 * The unnormalized ranker SUMMED idf over matched tokens and never divided by
 * how many tokens a fact had, so a fact carrying many aliases accumulated more
 * matches than a short one and won on incidental hits. Adding aliases made
 * ranking WORSE — 0.732 -> 0.659 rank@1 on the largest split, while every
 * matcher on the Nestor side improved. Aliases are the feature the retrieval
 * design is built around.
 *
 * Set `JARVIS_NO_LENGTH_NORM=1` to score the way jarvis used to, which is how
 * the two columns in the commit message were produced. Kept rather than deleted
 * because the before number is the entire evidence for the after one.
 *
 * The divisor mirrors `memory.js` exactly — sqrt(2.5*strong + weak), the same
 * 2.5 the scoring uses. Here every token is strong (no body text), so this is
 * sqrt(2.5) times sqrt(|strong|): a constant factor across facts, which cannot
 * reorder anything. The earlier sqrt(|strongTokens|) run therefore reproduces
 * exactly.
 */
const NORMALIZE = process.env.JARVIS_NO_LENGTH_NORM !== '1';

function factNorm(fact) {
  const strongCount = fact.strongTokens.length;
  const weakCount = Math.max(0, fact.tokens.length - strongCount);
  return Math.sqrt(2.5 * strongCount + weakCount) || 1;
}

function scoreArm(label, canonical, sealed, probes) {
  const facts = buildFacts(canonical, sealed);
  let rank1 = 0;
  let found = 0;
  for (const [span, ref] of probes) {
    const ranked = search(facts, span);
    if (ranked.length) found += 1;
    if (ranked.length && ranked[0].fact.id === ref) rank1 += 1;
  }
  const n = probes.length || 1;
  return { label, rank1: rank1 / n, anyHit: found / n, n: probes.length };
}

function rotate(sealed) {
  const refs = Object.keys(sealed).sort();
  if (refs.length < 2) return null;
  return Object.fromEntries(
    refs.map((r, i) => [r, sealed[refs[(i + 1) % refs.length]]]),
  );
}

const blocks = JSON.parse(readFileSync(process.argv[2] ?? 'terpsi_splits.json', 'utf8'));
console.log('jarvis ranker (IDF token overlap) on Nestor stage-3 splits\n');

for (const b of blocks) {
  const { canonical, sealed, probes } = b;
  const bare = Object.fromEntries(Object.keys(sealed).map((r) => [r, []]));
  const wrong = rotate(sealed);

  const arms = [
    scoreArm('canonical only', canonical, bare, probes),
    scoreArm('+ human surfaces', canonical, sealed, probes),
  ];
  if (wrong) arms.push(scoreArm('+ WRONG surfaces', canonical, wrong, probes));

  console.log(`${b.cut}  ${b.split}  (n=${probes.length})`);
  for (const a of arms) {
    console.log(
      `  ${a.label.padEnd(18)} rank@1=${a.rank1.toFixed(3)}   ` +
      `returned anything=${a.anyHit.toFixed(3)}`,
    );
  }
  console.log();
}
