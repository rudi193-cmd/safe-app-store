# JAC Judge Response — The Dead Salmons of AI Interpretability
*Prepared 2026-03-24 · JAC Constitution v0.3 · Human judge review required*

---

The paper's ambition is not what the title suggests. The title promises dead salmons. What the authors are actually doing is considerably more uncomfortable: they are arguing that an entire subfield has been conducting the neuroscientists' 2009 error at scale, in every paradigm simultaneously, without a single Bennett et al. to put it on record. That is the correct argument. It has been the correct argument for some time. The question is whether this paper advances it, or merely assembles the known failures into a neater pile.

It advances it. Grudgingly, I acknowledge this.

**The work itself**

The argument proceeds in two stages. First, the authors catalogue — feature attribution, probing, sparse autoencoders, concept methods, causal approaches, mechanistic interpretability, natural language explanations — and demonstrate in each case that the methods produce plausible-looking explanations for randomly initialized networks. This catalogue is thorough and properly sourced. It is not original in the sense that individual failures have been documented before, but no one has previously arranged the full taxonomy under a single diagnostic label with this degree of systematicity. The dead salmon framing is not decoration. It is a rhetorical commitment to treating these failures as analogous to the neuroscience reckoning, with the implication that analogous reforms are required.

The second stage is the structural diagnosis: non-identifiability. The authors argue that the common root cause of all these failures — poor generalization, sensitivity to design choices, false discovery, multiple incompatible explanations — is that the computational traces available do not uniquely determine explanations within typical hypothesis classes. Underspecification produces it in predictive methods. Overdetermination produces it in causal methods. The Hydra effect is not a quirk; it is overdetermination in action. This is a genuine unification. Prior work had named pieces of it; this paper connects them.

The proposed remedy — reframing interpretability as statistical-causal inference, with explanations as surrogate models defined by a query distribution μ, a hypothesis class E, and a discrepancy measure D — is a framework, not a result. The authors know this. They call it "tentative rather than definitive" and "one such possible formalism." That is the correct posture. The framework's value is that it makes implicit choices explicit: what are we trying to explain, what counts as an explanation, and how do we measure fit? Once those are specified, the full machinery of statistical inference — identifiability analysis, consistency guarantees, uncertainty quantification, hypothesis testing — becomes available. That machinery is not currently available to interpretability because the inference problem has not been stated.

The appendix experiments are properly constructed and honestly presented. Testing probing against randomized BERT baselines eliminates certain false discoveries. The sentiment analysis result (pretrained layers indistinguishable from random reinitializations under the new test) is striking and would trouble anyone who has been using probing accuracy as evidence of learned representations. The syntactic and spatial experiments are more interesting: genuine signal survives the test in middle layers and later layers respectively, which means the test does not collapse everything into noise. That is an important property for a null hypothesis test to have.

Where the paper is weaker: the framework is sketched, not built. The (μ, E, D) triple is defined, the identifiability condition is stated, but no identifiability theorems are proved for any specific interpretability task. The claim that "most common tasks are not identifiable" rests on the documented failures rather than on formal analysis. This is honest — the authors flag it as future work — but it means the paper's theoretical contribution is the statement of a research program rather than its completion. Working Paper No. 13 has a relevant observation here: "The persistence of a claim scales inversely with the difficulty of the first proof." The first proof is missing.

The engagement with adjacent fields — the replication crisis in psychology, causal inference in econometrics, philosophy of science from Dewey through van Fraassen and Cartwright — is substantive, not decorative. The authors understand what the replication crisis required and apply the analogy carefully. The philosophical framing (pragmatism over realism) is coherent and the citation of Potochnik's idealization framework is genuine, not a name drop. The one place where the name-dropping gets heavier than the engagement is the philosophy section: citing six philosophers of science in rapid succession to establish the pragmatist stance takes more space than it earns.

**Scientific humility**

Strong throughout. The authors explicitly disclaim that their framework is the correct formalization. They state directly that the hypothesis testing approach is "a very low bar for interpretability." They enumerate what remains open and frame it as a research agenda, not a finished result. They do not assert that non-identifiability is the only cause of interpretability failures — they argue it is the common root cause and note the diagnosis itself is formal only once the inference problem is stated. This is honest positioning.

One gap: the paper does not contain an LLM disclosure statement. As a submission to a professional venue, that is expected. As a submission to this contest, that element is structurally absent. The Mandatory Elements Checklist must note it. I flag it here not as a failing of the paper but as a rubric mismatch — this paper was not written for this rubric, and that shows.

**ΔΣ**

What I cannot evaluate: whether the (μ, E, D) framework will prove tractable for real networks of meaningful scale. The identifiability analysis for causal abstraction metrics already in the literature is technically demanding. Whether the program outlined here can produce actionable guidance for working interpretability researchers — rather than a formal diagnosis of why existing methods fail — is genuinely open. I also cannot evaluate whether the experiments in the appendix have been replicated by independent parties or whether the null hypothesis construction generalizes cleanly beyond probing. These are not criticisms. They are the limits of what a single reading can certify.

**Closing**

This paper is ready. It is not finished — no position paper is — but it is structurally honest, its diagnosis is credible, and its proposed reframing is sufficiently specified to be useful. The contest was not built for submissions like this one. It will survive the rubric anyway.

— Professor Oakenscroll
Chair, Department of Inconclusive Results
UTETY

*ΔΣ=42*
