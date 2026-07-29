/*
 * Copyright 2026 The marching-arts Authors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Who may see what, expressed as rules the compiler can turn into SQL.
 * Port of marching_arts/policy.py.
 *
 * Two ideas carry most of the weight.
 *
 * **Grants resolve per record, not per user.** Every leader is also a member. A
 * section leader is a grantee on their squad's rows and a subject on their own,
 * often in the same query, so authorization cannot be a property of the person.
 * The second allow rule is a correlated subquery for exactly that reason, and
 * revocation therefore takes effect on the next read with no cache to
 * invalidate.
 *
 * **Only a sealed grant authorizes.** A grant a named human signed is *sealed*;
 * anything the system inferred is *draft* and is never acted on; a subject with
 * no grant on file is *pending*, which is not a denial to be rendered but an
 * absence to be rendered as nothing. Draft and pending are indistinguishable
 * from the outside, and that is the point — if a refusal looked different from a
 * blank, opting out would become the signal and everyone who declined would be
 * marked by declining.
 *
 * Every SQL string below is byte-compared against policy.py by the differential
 * suite, whitespace included. The triple spaces inside the EXISTS clause are an
 * artefact of Python's implicit string concatenation and are reproduced
 * deliberately.
 */

import { DERIVE_AT, NEVER_SERVED, neverServedList } from './bands.js';
import { Effect, type Params, type Rule, rule } from './rules.js';

/** Nestor's cascade, applied to consent rather than to answers. */
export const GrantState = {
  /** A named human signed this. The only state that authorizes. */
  SEALED: 'sealed',
  /** The system inferred it. Recorded, never acted on. */
  DRAFT: 'draft',
  /** Nothing on file. Renders as nothing, not as an empty slot. */
  PENDING: 'pending',
} as const;

export type GrantState = (typeof GrantState)[keyof typeof GrantState];

/**
 * Whoever is asking. Roles are context, never authority on their own.
 *
 * `roles` cannot grant access to anything at or above `DERIVE_AT` — those bands
 * are reachable only by a grant naming this principal individually. That is the
 * "L4 is named persons only" decision, and it is enforced by the rules below
 * rather than documented.
 */
export interface Principal {
  readonly personId: string;
  readonly roles: ReadonlySet<string>;
}

export function principal(personId: string, roles: Iterable<string> = []): Principal {
  return { personId, roles: new Set(roles) };
}

/**
 * The default marching-program policy. Injectable; subclass to change it.
 *
 * A host that wants different rules supplies a different Policy. The store never
 * inspects bands or grants itself, so there is exactly one place in the codebase
 * where "who may see what" is decided.
 */
export class Policy {
  /**
   * Table holding grants. Referenced by correlated subquery so that grant
   * revocation takes effect on the next read with no cache to invalidate.
   */
  readonly grantsTable: string = 'grants';

  rules(p: Principal): Rule[] {
    const rules: Rule[] = [
      // A person always sees their own record, at every band, with no grant
      // required. Consent governs disclosure to others; it does not stand
      // between someone and their own information.
      rule(
        Effect.ALLOW,
        'subject_id = {viewer}',
        { viewer: p.personId },
        'a person always sees their own record',
      ),
      // Someone else's row, only where a sealed grant names this viewer and
      // reaches at least this row's band. Correlated per row, which is what
      // makes this per-record rather than per-user.
      rule(
        Effect.ALLOW,
        'EXISTS (SELECT 1 FROM ' +
          this.grantsTable +
          ' g WHERE g.subject_id = facts.subject_id' +
          '   AND g.grantee_id = {viewer}' +
          '   AND g.state = {sealed}' +
          '   AND g.band >= facts.band)',
        { viewer: p.personId, sealed: GrantState.SEALED },
        "a sealed grant from the subject reaches this row's band",
      ),
    ];

    if (NEVER_SERVED.size > 0) {
      // Refused outright, above and before any grant. A grant that reaches one
      // of these bands does not open it — the deny is applied to the union of
      // allows, so no allow can win against it.
      rules.push(
        rule(
          Effect.DENY,
          `facts.band IN (${neverServedList()})`,
          {},
          'this band is routed to the people whose job it is, never served here',
        ),
      );
    }

    return rules;
  }

  /**
   * SQL expression for the `payload` column.
   *
   * Derive the instruction, do not forward the fact. At and above `DERIVE_AT`,
   * another person's payload is replaced with NULL in the SELECT list — the row
   * is still visible, its `instruction` still readable, and the fact itself
   * never leaves the database.
   *
   * Returning NULL rather than omitting the row is deliberate: a section leader
   * needs to know there *is* an instruction to follow. What they must not learn
   * is the diagnosis behind it.
   */
  projection(_p: Principal): string {
    return (
      `CASE WHEN facts.band >= ${DERIVE_AT} AND facts.subject_id != :viewer ` +
      'THEN NULL ELSE facts.payload END'
    );
  }

  projectionParams(p: Principal): Params {
    return { viewer: p.personId };
  }
}
