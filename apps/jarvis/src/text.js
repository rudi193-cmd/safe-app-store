// Tokenising and stemming.
//
// Shared by the write path (which tokenises a fact into the inverted index)
// and the read path (which tokenises a query). They have to agree exactly —
// a stemmer that behaves differently on write and read produces an index
// nothing can find, and the failure is silent because both halves look
// correct in isolation. There is a test that runs a phrase through both
// paths and asserts they meet.

export const STOPWORDS = new Set(
  ('a about all also am an and any are as at be because been but by can could did do does doing done for from get gets ' +
   'getting got had has have having he her hers him his how i if in into is it its just know let like me might my need ' +
   'no not now of on once only or other our out over own please said same she should so some such than that the their ' +
   'them then there these they this those through to too under until up us very want was way we were what when where ' +
   'which while who why will with would you your yours thanks thank tell').split(' '),
);

/**
 * Conservative suffix stripping. Not Porter — deliberately.
 *
 * Porter is aggressive enough to collapse words that mean different things
 * ("universal" and "university" both to "univers"), and in a personal memory
 * a false match is worse than a miss: a miss is silence, a false match is the
 * assistant confidently telling you something about the wrong subject. This
 * handles plurals and the common verb endings and stops there.
 */
export function stem(word) {
  let w = String(word).toLowerCase();
  if (w.length <= 3) return w;

  if (w.endsWith('ies') && w.length > 4) return `${w.slice(0, -3)}y`;
  if (w.endsWith('sses')) return w.slice(0, -2);
  if (w.endsWith('ses') && w.length > 4) return w.slice(0, -2);
  if (w.endsWith('s') && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);

  // Verb and adverb endings are only stripped when what is left is still at
  // least four characters — long enough to plausibly be a word. Without that
  // floor, "string" becomes "str" and "spring" becomes "spr", which collide
  // with anything else beginning those letters. The cost of the floor is that
  // short forms like "asked" keep their ending and so never match "ask".
  // That is a miss, and a miss is silence; the alternative is a false match,
  // which is the assistant saying something confident about the wrong thing.
  // Aliases are what cover the misses.
  w = stripSuffix(w, 'ing', 4) ?? stripSuffix(w, 'edly', 4) ?? stripSuffix(w, 'ed', 4) ?? stripSuffix(w, 'ly', 4) ?? w;

  return w;
}

function stripSuffix(word, suffix, minRemaining) {
  if (!word.endsWith(suffix)) return null;
  const remaining = word.slice(0, -suffix.length);
  if (remaining.length < minRemaining) return null;
  return suffix === 'ly' ? remaining : undouble(remaining);
}

/** "getting" -> "gett" -> "get". Doubled consonants that carry meaning are kept. */
function undouble(w) {
  if (w.length > 3 && /([bcdfgklmnprtvz])\1$/.test(w)) return w.slice(0, -1);
  return w;
}

/**
 * Text to a deduplicated token list: lowercase, split on anything that is not
 * a letter or digit, drop stopwords and single characters, stem the rest.
 */
export function tokenize(text) {
  const out = new Set();
  for (const raw of String(text || '').toLowerCase().split(/[^a-z0-9]+/)) {
    if (raw.length < 2) continue;
    if (STOPWORDS.has(raw)) continue;
    const s = stem(raw);
    if (s.length < 2) continue;
    if (STOPWORDS.has(s)) continue;
    out.add(s);
  }
  return [...out];
}

/**
 * The token sets for a fact.
 *
 * `strong` is the subject and its aliases — the words someone would use to
 * *look this up*. `all` adds the body text, which is worth indexing but is
 * weaker evidence: a word buried in a sentence is often incidental, whereas a
 * word in the subject or an alias was put there to be found. The ranker
 * weights the two differently rather than treating a passing mention as
 * equivalent to a deliberate label.
 */
export function tokensFor({ subject = '', aliases = [], text = '' }) {
  const strong = new Set([...tokenize(subject), ...aliases.flatMap((a) => tokenize(a))]);
  const all = new Set([...strong, ...tokenize(text)]);
  return { strong: [...strong], all: [...all] };
}
