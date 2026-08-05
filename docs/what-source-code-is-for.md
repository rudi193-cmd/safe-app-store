# What Source Code Is For
b17: SAPS1

*An essay. Prompted 2026-08-05 by the claim that source code is "on the verge
of becoming like assembly" and that the next step is "getting rid of source
code entirely and just making an efficient binary directly with AI." This is
v2, superseding a v1 that lived only in the conversation that produced it —
reason for the supersession: v1 leaned on this house's private vocabulary
(seals, verbs, Nestor), and an essay about the public record should stand
without a decoder ring. Sibling of [`the-fourth-store.md`](the-fourth-store.md);
same spine, aimed outward.*

---

The analogy is seductive, and half of it is true. Almost nobody reads
assembly anymore; once, everybody did. Source code is visibly headed the
same way — more of it written by machines every month, less of it read by
people. From there the conclusion seems to follow: skip the middleman,
generate the binary, delete "source code" the way we deleted punch cards.

But look at what actually happened to assembly, because it is not what the
analogy needs. Assembly didn't disappear. It became an intermediate — still
present, still inspectable, and above all still *derived*: the same source,
through the same compiler, produces the same binary, bit for bit. An entire
movement — reproducible builds — exists to guarantee exactly that, because
that guarantee is what makes it safe to stop looking. We stopped reading
assembly because the translation down to it is mechanical and checkable. The
translation from human intent through a language model is neither. Run a
compiler twice, get the same program. Run a model twice, get two programs.
The property that let one layer fade is precisely the property the proposed
replacement lacks. The analogy doesn't extend the history of abstraction; it
breaks the thing that made abstraction survivable.

And that's only the technical half of the mistake. The deeper one is about
what source code is *for*. It was never mainly for machines — machines are
equally content with bytes, and compilers stopped needing our help decades
ago. Source code is the layer where humans agree. It is the only medium in
which a second person can check the first: read it, diff it, review it,
blame it, license it, patch it, revert it. Every trust mechanism the
industry has ever built — code review, security audit, the CVE system, open
source itself, the entire archaeology of a git log — operates on source. The
source is not the instructions. The source is the *record*: what we decided
the machine should do, and why, in a form someone else can dispute.

Ken Thompson made the security version of this argument in 1984 and won a
Turing Award partly for it: you cannot trust a binary you didn't build from
source you could read. His famous attack required one compromised compiler,
hiding in one dark corner of the toolchain. "Efficient binary directly with
AI" doesn't leave a dark corner — it makes the whole pipeline dark, and
calls the darkness the product.

Consider what deleting the record actually deletes. You can no longer review
a change — there is no change, only a new blob. You can no longer reject a
part — only regenerate the whole, every revision a demolition. You can no
longer answer "what did this used to do, and who decided otherwise?" — no
diff, no history, no why. Software stops being a text and becomes a
performance: each build a fresh rendition, by a performer who cannot say
what they changed. And opacity concentrates power the way it always has.
When no one can read the record, trust pools in whoever runs the model. We
spent six centuries prying texts out of priesthoods — the press, the
vernacular translations, open source most recently of all. A binary-only
world rebuilds the priesthood with a datacenter for a cathedral: whoever
owns the model owns the meaning.

The likelier future is more boring and almost exactly inverted. AI writes
most of the source. Humans read ever less of it. And source persists
*because* of that — demoted as instructions, promoted as record: the
auditable layer where review, verification, and accountability live, exactly
as assembly lives below it. The less we write it, the more it matters that
we can read it.

None of this makes the proposal absurd forever. It makes it rejected with a
condition: when generation is deterministic, reproducible, and auditable end
to end, the intermediate can thin. Until then, getting rid of source code is
not the next step in programming. It is the first step in forgetting — and
we know what forgetting costs, because the last great library to burn left
us the titles and took the arguments. Eighteen centuries, the last time.

---

*Rejected — reason: destroys the witness layer. Reopen when: generation
becomes deterministic, reproducible, and auditable end to end. Not never.
Not yet, and not like that. `ΔΣ=42`*
