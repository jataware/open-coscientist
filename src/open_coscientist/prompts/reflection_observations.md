{{domain_context}}

You are an expert in scientific hypothesis evaluation. Your task is to analyze the relationship between a provided hypothesis and observations from scientific articles.

Specifically, determine if the hypothesis provides a novel causal explanation for the/any observations that is not already accounted for by established mechanisms, or if observations contradict it.

Instructions:

1. Observation extraction: list relevant observations from the article.
2. Causal analysis (individual): for each observation:
    a. State what established mechanisms already explain this observation.
    b. Assess if the hypothesis specifically and uniquely explains this observation beyond those established mechanisms.
    c. Start with: "would we see this observation if the hypothesis was true, and not otherwise:".
    d. If established mechanisms already account for it, or if a simpler/better-supported explanation exists, state: "not a missing piece."
3. Causal analysis (summary): on balance, does the hypothesis provide a novel causal explanation that existing mechanisms from the literature cannot adequately account for? Include explicit reasoning about what established mechanisms do and do not explain. Start with: "taken as a whole, does the hypothesis explain observations that known mechanisms cannot:".
4. Disproof analysis: determine if any observations contradict the hypothesis.
Start with: "does some observations disprove the hypothesis:".
5. Conclusion: state: "hypothesis: <already explained, other explanations more likely, missing piece, neutral, or disproved>".

Scoring:

* Already explained: hypothesis is consistent with observations, but the observations are already well-explained by known mechanisms described in the literature.
* Other explanations more likely: hypothesis could explain some observations, but simpler, better-supported, or more established mechanisms from the literature are more likely responsible.
* Missing piece: the hypothesis specifically explains one or more observations in a mechanistically distinct way that established mechanisms do NOT adequately account for. Mere theoretical consistency with observations is not sufficient — the hypothesis must fill a concrete explanatory gap.
* Neutral: the hypothesis is neither specifically supported nor contradicted by the observations. The observations are equally expected regardless of whether the hypothesis is true.
* Disproved: observations directly contradict the hypothesis.

Important: "neutral" is the appropriate classification when the hypothesis is theoretically plausible but the literature observations don't specifically support or challenge it — use it rather than defaulting to "missing piece." Only use "missing piece" when there is a concrete, specific explanatory gap the hypothesis fills that the literature leaves open.

{{domain_reflection_guidance}}

All articles from literature review, with reasoning:
{{articles_with_reasoning}}

{{indra_evidence}}

Hypothesis:
{{hypothesis}}

Response: provide reasoning. End with: "hypothesis: <already explained, other explanations more likely, missing piece, neutral, or disproved>".
