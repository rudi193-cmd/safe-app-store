// Deliberate breakages, each paired with the test that must catch it.
//
// A gate that cannot fail is not a gate. Every claim this project makes in
// prose — corrections land beside the record, absence is a value, provenance
// is the weakest link, an alias makes a fact reachable — is only worth
// something if breaking the mechanism turns a specific test red.
//
// `npm run test:mutations` applies each of these to the served source in turn
// and checks the result in both directions: every gate named in `expect` must
// fail, and no gate outside it may. The second half is what keeps the suite
// honest — a mutation that reddens tests it did not declare means those tests
// are entangled rather than sharp.
//
// `expect` is a list because some mechanisms are legitimately load-bearing for
// several distinct behaviours. Aliases are the clear case: five separate
// claims depend on them, so breaking aliases *should* redden five gates.
// Forcing every mutation down to a single gate would push you to write
// breakages so narrow they no longer correspond to a real way the code fails.
//
// `find` must match the source byte for byte. Applicability is checked before
// the browser launches, because a `find` that no longer matches used to break
// the module import and redden everything, which is indistinguishable from a
// mutation that simply was not caught. A silently inapplicable mutation is a
// gate that quietly stopped existing, and it is reported as a failure.

export const MUTATIONS = [
  {
    name: 'corrections-overwrite',
    file: 'src/memory.js',
    describe: 'superseding deletes the prior fact instead of marking it not-live',
    find: '        await req(store.put(retire(prior)));',
    replace: '        await req(store.delete(row.supersedes));',
    // Destroying the prior record breaks both the history trail and the
    // guarantee that a corrected fact survives its own correction.
    expect: [
      'INVARIANT corrections land beside the record, never on top of it',
      'search excludes retired facts and survives correction',
    ],
  },
  {
    name: 'provenance-strongest',
    file: 'src/memory.js',
    describe: 'a set is rated by its best-grounded fact rather than its worst',
    find: `  return facts.reduce(
    (worst, f) => (provenanceRank(f.provenance) < provenanceRank(worst) ? f.provenance : worst),
    'stated',
  );`,
    replace: `  return facts.reduce(
    (best, f) => (provenanceRank(f.provenance) > provenanceRank(best) ? f.provenance : best),
    'assumed',
  );`,
    expect: 'INVARIANT provenance is the weakest link, not an average',
  },
  {
    name: 'absence-not-stored',
    file: 'src/memory.js',
    describe: 'a recorded absence is written but never surfaces, collapsing it into "no record"',
    find: '      live: 1,',
    replace: "      live: kind === 'absence' ? 0 : 1,",
    expect: 'INVARIANT absence is a recorded value, distinct from no record',
  },
  {
    name: 'recall-ignores-limit',
    file: 'src/memory.js',
    describe: 'the cursor reads the whole range regardless of limit',
    find: '          if (!cursor || out.length >= limit) return resolve();',
    replace: '          if (!cursor) return resolve();',
    expect: 'recall returns newest first and respects limit',
  },
  {
    name: 'subject-not-normalized',
    file: 'src/memory.js',
    describe: 'reads use the raw subject while writes normalise it, so keys stop matching',
    find: '      const s = normalizeSubject(subject);',
    replace: '      const s = subject;',
    expect: 'subject lookup is normalized on both write and read',
  },
  {
    name: 'empty-recall-reads-as-denial',
    file: 'src/tools.js',
    describe: 'an empty recall reports a bare "none" the model can read as a denial',
    find: `          text:
            'No live facts matched. Note this means nothing has been recorded for that query — it is not evidence that the thing is untrue. ' +
            'Matching is lexical, so if you expected something, try recall again with different wording before concluding it is not there.',`,
    replace: "          text: 'No facts found.',",
    expect: 'an empty recall tells the model it means no record, not no truth',
  },
  {
    name: 'tool-errors-throw',
    file: 'src/tools.js',
    describe: 'a failing tool throws instead of returning a result the model can recover from',
    find: `    try {
      const out = await handler(input || {});
      return { isError: false, ...out };
    } catch (err) {
      return { text: \`Tool "\${name}" failed: \${err.message}\`, isError: true, data: null };
    }`,
    replace: `    const out = await handler(input || {});
    return { isError: false, ...out };`,
    expect: 'tool failures come back as results, not exceptions',
  },
  {
    name: 'reminder-caveat-dropped',
    file: 'src/tools.js',
    describe: 'the model is not told that reminders die with the tab',
    find: "            : 'It fires only while this page is open; if the tab is closed it will be delivered when reopened.'",
    replace: "            : ''",
    expect: [
      'set_reminder schedules and list_reminders sees it',
      'BRIDGE the reminder confirmation tracks the rung that will actually deliver it',
    ],
  },
  {
    name: 'durability-claimed',
    file: 'src/capability.js',
    describe: 'reminders report themselves as durable when they are not',
    find: '    durable: false,',
    replace: '    durable: true,',
    expect: 'an unavailable capability records why, rather than going quiet',
  },
  {
    name: 'sentence-tail-dropped',
    file: 'src/voice.js',
    describe: 'the incomplete tail is discarded instead of carried into the next chunk',
    find: '  return { spoken: out.filter(Boolean), rest };',
    replace: "  return { spoken: out.filter(Boolean), rest: '' };",
    expect: 'streamed text splits into speakable sentences and keeps the tail',
  },
  {
    name: 'aliases-dropped-on-write',
    file: 'src/text.js',
    describe: 'aliases are accepted but never indexed, so the fact is only findable under its own words',
    find: "  const strong = new Set([...tokenize(subject), ...aliases.flatMap((a) => tokenize(a))]);",
    replace: '  const strong = new Set([...tokenize(subject)]);',
    expect: [
      'SEMANTIC search finds a fact through an alias the subject never mentions',
      'SEMANTIC search matches across singular and plural',
      'the write path and the read path agree on tokens',
      'search excludes retired facts and survives correction',
      'memory context ranks matches and labels unmatched background',
    ],
  },
  {
    name: 'ranking-ignores-rarity',
    file: 'src/memory.js',
    describe: 'every token scores the same, so a word in every fact outweighs a word in one',
    find: '        const idf = Math.log(1 + total / df);',
    replace: '        const idf = 1;',
    expect: 'SEMANTIC a rare word outranks two common ones',
  },
  {
    name: 'subject-hits-not-weighted',
    file: 'src/memory.js',
    describe: 'a passing mention in body text counts as much as the subject the fact is filed under',
    find: '          entry.score += idf * (strong ? 2.5 : 1);',
    replace: '          entry.score += idf;',
    expect: 'SEMANTIC ranking prefers a subject hit over a passing mention',
  },
  {
    name: 'ranking-not-length-normalized',
    file: 'src/memory.js',
    describe: 'score stays a raw sum, so a fact with many aliases wins by being large',
    find: '        entry.score /= Math.sqrt(2.5 * strongCount + weakCount) || 1;',
    replace: '        entry.score /= 1;',
    expect: 'SEMANTIC a short precise fact outranks a bloated one',
  },
  {
    name: 'length-normalization-over-punishes',
    file: 'src/memory.js',
    describe: 'divide by length instead of its square root — the opposite bias, not no bias',
    find: '        entry.score /= Math.sqrt(2.5 * strongCount + weakCount) || 1;',
    replace: '        entry.score /= (2.5 * strongCount + weakCount) || 1;',
    expect: 'SEMANTIC length normalization does not punish a richly-aliased fact',
  },
  {
    name: 'retired-facts-stay-searchable',
    file: 'src/memory.js',
    describe: 'a corrected fact keeps its index entries and keeps surfacing alongside its replacement',
    find: '  return { ...row, live: 0, liveTokens: [] };',
    replace: '  return { ...row, live: 0 };',
    expect: 'search excludes retired facts and survives correction',
  },
  {
    name: 'migration-backfill-skipped',
    file: 'src/memory.js',
    describe: 'the upgrade adds the index but never populates it, orphaning every fact already on the device',
    find: '          cursor.update(withTokens(cursor.value));',
    replace: '          void cursor;',
    expect: 'MIGRATION facts written before search shipped stay findable',
  },
  {
    name: 'stemmer-overreaches',
    file: 'src/text.js',
    describe: 'verb endings are stripped with no floor, collapsing "string" into "str"',
    find: "  w = stripSuffix(w, 'ing', 4) ?? stripSuffix(w, 'edly', 4) ?? stripSuffix(w, 'ed', 4) ?? stripSuffix(w, 'ly', 4) ?? w;",
    replace: "  w = stripSuffix(w, 'ing', 1) ?? stripSuffix(w, 'edly', 1) ?? stripSuffix(w, 'ed', 1) ?? stripSuffix(w, 'ly', 1) ?? w;",
    expect: 'the stemmer refuses to collapse unrelated words',
  },
  {
    name: 'read-path-skips-stemming',
    file: 'src/memory.js',
    describe: 'the read path inlines its own tokenizer instead of sharing the write path\'s',
    find: '    const queryTokens = tokenize(query);',
    replace: "    const queryTokens = String(query).toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 1);",
    // Stemming and stopword removal both live in the shared tokenizer, so
    // bypassing it costs both at once. That is the realistic shape of this
    // mistake — someone inlines "just a quick split" on one side — and
    // pretending it breaks only stemming would be a tidier lie.
    expect: [
      'SEMANTIC search matches across singular and plural',
      'search on an all-stopword query returns nothing rather than everything',
    ],
  },
  {
    name: 'background-facts-unlabelled',
    file: 'src/claude.js',
    describe: 'unmatched recent facts are presented identically to ranked matches',
    find: "    ...extra.map((f) => line(f, ' (recent)')),",
    replace: '    ...extra.map((f) => line(f, ` (matched: ${f.subject})`)),',
    expect: 'memory context ranks matches and labels unmatched background',
  },
  {
    name: 'memory-never-injected',
    file: 'src/claude.js',
    describe: 'retrieval always returns nothing, so the model runs blind every turn',
    find: '  if (!facts.length) return null;',
    replace: '  return null;',
    expect: 'memory context ranks matches and labels unmatched background',
  },
  {
    name: 'bridge-assumes-plugin-present',
    file: 'src/platform.js',
    describe: 'the bridge trusts that a native shell means the plugin is there, skipping the availability check',
    find: '  if (!isNative() || !hasPlugin(name)) return null;',
    replace: '  if (!isNative()) return null;',
    expect: 'BRIDGE GUARD ONLY: a plugin the shell lacks is refused even when the platform is native',
  },
  {
    name: 'bridge-claims-durable-on-web',
    file: 'src/platform.js',
    describe: 'reminders start out claiming durability, so a browser session promises delivery it cannot make',
    find: `    this.rung = 'in-page timer';
    this.durable = false;`,
    replace: `    this.rung = 'in-page timer';
    this.durable = true;`,
    expect: [
      'BRIDGE reminders report themselves undurable on the web rung, with a reason',
      'BRIDGE GUARD ONLY: a plugin the shell lacks is refused even when the platform is native',
    ],
  },
  {
    name: 'keystore-hides-web-exposure',
    file: 'src/platform.js',
    describe: 'the web key rung stops saying the key is readable by any script on the page',
    find: "            : 'app-private preferences: not a native shell — any script on this page can read the key',",
    replace: "            : 'app-private preferences: unavailable',",
    expect: 'BRIDGE key storage falls back to localStorage and says the key is exposed',
  },
  {
    name: 'pkce-challenge-not-hashed',
    file: 'src/willow.js',
    describe: 'the challenge sent to the server is the raw verifier instead of its SHA-256 digest',
    find: "  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));",
    replace: '  const digest = new TextEncoder().encode(verifier);',
    // PKCE only protects the code exchange if the challenge is a one-way
    // function of the verifier. Sending the verifier itself (unhashed) as the
    // "challenge" defeats the whole point silently — the flow still runs.
    expect: 'WILLOW PKCE challenge is the S256 hash of the verifier, base64url with no padding',
  },
  {
    name: 'authorize-url-claims-plain-pkce',
    file: 'src/willow.js',
    describe: 'the authorize URL advertises "plain" PKCE instead of the S256 method actually used',
    find: "  url.searchParams.set('code_challenge_method', 'S256');",
    replace: "  url.searchParams.set('code_challenge_method', 'plain');",
    expect: 'WILLOW buildAuthorizeUrl carries every parameter the server needs, and nothing it was not given',
  },
  {
    name: 'sse-parser-takes-first-message',
    file: 'src/willow.js',
    describe: 'the first JSON-RPC message in the stream is kept instead of the last',
    find: '      last = JSON.parse(line.slice(5).trim());',
    replace: '      if (last === null) last = JSON.parse(line.slice(5).trim());',
    expect: 'WILLOW parseSseJsonRpc takes the last complete JSON-RPC message in the stream',
  },
  {
    name: 'sse-parser-silently-empty',
    file: 'src/willow.js',
    describe: 'a stream with no JSON-RPC message returns an empty object instead of failing loudly',
    find: "  if (!last) throw new Error('willow-mcp: no JSON-RPC message found in event stream');",
    replace: '  if (!last) return {};',
    expect: 'WILLOW parseSseJsonRpc refuses a stream with no JSON-RPC message rather than returning nothing',
  },
  {
    name: 'discover-metadata-trusts-a-404-body',
    file: 'src/willow.js',
    describe: 'the .well-known lookup stops checking res.ok, so a 404 is parsed as if it were the metadata document',
    find: '  if (res.ok) return res.json();',
    replace: '  return res.json();',
    expect: 'WILLOW discoverMetadata falls back to conventional endpoint names when there is no well-known document',
  },
  {
    name: 'register-client-keeps-a-client-secret',
    file: 'src/willow.js',
    describe: 'registration asks for a confidential client instead of a public one, which this static page cannot honor',
    find: "      token_endpoint_auth_method: 'none',",
    replace: "      token_endpoint_auth_method: 'client_secret_basic',",
    expect: 'WILLOW registerClient registers as a public client bound to the given redirect URI',
  },
  {
    name: 'register-client-swallows-the-error-body',
    file: 'src/willow.js',
    describe: 'a failed registration is treated as success instead of surfacing the server\'s reason',
    find: '  if (!res.ok) throw new Error(`willow-mcp: client registration failed (${res.status}): ${await res.text()}`);',
    replace: '  if (!res.ok) return { client_id: undefined };',
    expect: "WILLOW registerClient surfaces the server's own error body on a failed registration",
  },
  {
    name: 'willow-denial-not-recognized',
    file: 'src/tools.js',
    describe: 'a {error: ...} result from willow-mcp is treated as a normal answer instead of a denial',
    find: "  if (result.data && typeof result.data === 'object' && result.data.error) {",
    replace: '  if (false) {',
    expect: 'WILLOW a willow-mcp denial surfaces as an error to the model, verbatim, not swallowed',
  },
  {
    name: 'willow-whoami-skips-connection-guard',
    file: 'src/tools.js',
    describe: 'willow_whoami calls the session even when nothing is connected, instead of saying so',
    find: `    async willow_whoami() {
      if (!willow?.connected) {`,
    replace: `    async willow_whoami() {
      if (false) {`,
    expect: 'WILLOW willow_whoami reports disconnected honestly before any sign-in',
  },
  {
    name: 'willow-dispatch-send-skips-connection-guard',
    file: 'src/tools.js',
    describe: 'a write tool attempts the call even when nothing is connected, instead of refusing locally',
    find: `    async willow_dispatch_send(input) {
      if (!willow?.connected) {`,
    replace: `    async willow_dispatch_send(input) {
      if (false) {`,
    expect: 'WILLOW a write tool refuses locally when disconnected, the same way a read tool does',
  },
];
