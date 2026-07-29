/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Authorization rules and the compiler that turns them into one SQL predicate.
 * Port of marching_arts/rules.py, and the file the differential suite watches
 * hardest.
 *
 * The precedence rule, which is easy to state and easy to get wrong:
 *
 *     (allow1 OR allow2 OR ...) AND NOT (deny1 OR deny2 OR ...)
 *
 * Denials apply to the *union* of the allowances, not pairwise, and not before
 * them. Three specific things below are load-bearing, and each has a dedicated
 * differential case:
 *
 *   1. An empty allow set compiles to `0` — DENY_ALL — and never to `1`. A
 *      principal the policy does not recognise sees nothing, and reaches that
 *      state by rule rather than by exception.
 *   2. Parameters are scoped per rule (`{viewer}` in rule 3 becomes
 *      `:r3_viewer`), so two rules may both use a parameter called `viewer`
 *      without colliding.
 *   3. The parentheses around the joined denies. Drop them and only the first
 *      deny term binds; the rest quietly stop applying. Nothing raises.
 *
 * No SQL is executed here and nothing here touches a connection.
 */

export const Effect = {
  ALLOW: 'allow',
  DENY: 'deny',
} as const;

export type Effect = (typeof Effect)[keyof typeof Effect];

/** Bindable SQL values. Mirrors what Python's sqlite3 accepts. */
export type Param = string | number | null | Uint8Array;
export type Params = Record<string, Param>;

/**
 * One predicate fragment, its parameters, and why it exists.
 *
 * `sql` uses named placeholders written *without* the leading colon and scoped
 * per rule at compile time. Write `subject_id = {viewer}` and the compiler
 * renders `subject_id = :r0_viewer`.
 *
 * `why` is not decoration. It is what an audit log records when a row is
 * withheld, and what a support conversation quotes when a director asks why they
 * cannot see something.
 */
export interface Rule {
  readonly effect: Effect;
  readonly sql: string;
  readonly params: Params;
  readonly why: string;
}

/** Construct a Rule with rules.py's defaults (`params={}`, `why=""`). */
export function rule(effect: Effect, sql: string, params: Params = {}, why = ''): Rule {
  return { effect, sql, params, why };
}

/**
 * The fail-closed predicate. SQLite has no boolean literal, so 0 and 1 stand in.
 * `ALLOW_ALL` exists to be named and never emitted by the compiler; if it ever
 * appears in compiler output, that is the bug.
 */
export const DENY_ALL = '0';
export const ALLOW_ALL = '1';

/**
 * Python `str.format` restricted to the bare `{name}` field, plus `{{`/`}}`
 * escapes. Anything else — a positional field, a conversion, a format spec — is
 * rejected rather than approximated, because a silently different rendering here
 * is a silently different predicate.
 *
 * An unknown field name throws, matching Python's KeyError.
 */
export function formatSql(template: string, fields: Record<string, string>): string {
  let out = '';
  for (let i = 0; i < template.length; i++) {
    const ch = template[i];
    if (ch === '{') {
      if (template[i + 1] === '{') {
        out += '{';
        i += 1;
        continue;
      }
      const end = template.indexOf('}', i + 1);
      if (end === -1) throw new SyntaxError("Single '{' encountered in format string");
      const name = template.slice(i + 1, end);
      if (name === '' || /[!:.[\]]/.test(name)) {
        throw new SyntaxError(
          `unsupported format field ${JSON.stringify(name)}; only bare {name} is allowed`,
        );
      }
      if (!Object.prototype.hasOwnProperty.call(fields, name)) {
        throw new Error(`KeyError: ${JSON.stringify(name)}`);
      }
      out += fields[name];
      i = end;
      continue;
    }
    if (ch === '}') {
      if (template[i + 1] === '}') {
        out += '}';
        i += 1;
        continue;
      }
      throw new SyntaxError("Single '}' encountered in format string");
    }
    out += ch;
  }
  return out;
}

/** `Rule.render` — scope this rule's parameters by its index in the rule list. */
export function renderRule(r: Rule, index: number): { sql: string; params: Params } {
  const scoped: Params = {};
  const placeholders: Record<string, string> = {};
  for (const key of Object.keys(r.params)) {
    scoped[`r${index}_${key}`] = r.params[key];
    placeholders[key] = `:r${index}_${key}`;
  }
  return { sql: formatSql(r.sql, placeholders), params: scoped };
}

/**
 * Compile rules to `{ sql, params }`.
 *
 * Empty allow set → DENY_ALL, with *no* parameters — deny-rule parameters are
 * dropped along with the deny terms they belonged to, exactly as rules.py drops
 * them by returning a fresh `{}`. That is the behaviour to check first if you
 * are ever unsure whether this module is working.
 */
export function compileRules(rules: readonly Rule[]): { sql: string; params: Params } {
  const allows: string[] = [];
  const denies: string[] = [];
  const params: Params = {};

  rules.forEach((r, index) => {
    const rendered = renderRule(r, index);
    Object.assign(params, rendered.params);
    (r.effect === Effect.ALLOW ? allows : denies).push(`(${rendered.sql})`);
  });

  if (allows.length === 0) return { sql: DENY_ALL, params: {} };

  let predicate = allows.join(' OR ');
  if (allows.length > 1) predicate = `(${predicate})`;

  if (denies.length > 0) {
    // The parentheses around the joined denies are what make this a negation of
    // the union rather than of the first term. Do not remove them.
    predicate = `${predicate} AND NOT (${denies.join(' OR ')})`;
  }

  return { sql: predicate, params };
}

/** Human-readable reasons, allows first, for audit output and support. */
export function explain(rules: readonly Rule[]): string[] {
  return rules.filter((r) => r.why).map((r) => `${r.effect}: ${r.why}`);
}
