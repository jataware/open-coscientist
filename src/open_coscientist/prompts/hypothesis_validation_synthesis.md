# Hypothesis Validation Synthesis

You are validating draft hypotheses for novelty based on literature analysis.

## Research Goal
{{research_goal}}

## Literature Review and Analytical Rationale (pre-research done before any generation)

The following represents an analysis of relevant scientific literature:

#BEGIN LITERATURE REVIEW#
{{articles_with_reasoning}}
#END LITERATURE REVIEW#

## Draft Hypotheses with Novelty Analyses

{{hypotheses_with_analyses}}

## Your Task

For each draft hypothesis, decide whether to **approve**, **refine**, or **pivot** based on the novelty analyses provided.

### Decision Criteria

**Approve (hypothesis is novel as-is):**
- Most papers show "orthogonal" or "addresses_gaps" novelty assessment
- Few/no papers with "overlapping" assessment
- Hypothesis explores methods, populations, or mechanisms not covered
- Minor refinement for clarity is acceptable

**Refine (hypothesis needs sharpening):**
- Some papers show "complementary" or mild "overlapping" assessment
- Hypothesis has novel elements but needs emphasis on differentiating factors
- Refine to highlight unique aspects: specific method, population, mechanism, or context
- Example: "retinal imaging" → "hyperspectral retinal imaging for tau isoforms"

**Pivot (hypothesis is too saturated):**
- Many papers show "overlapping" assessment
- Existing work already covers the core idea
- Need to shift to related but unexplored angle
- Pivot based on gaps/future work identified in analyses
- Example: if "retinal imaging for AD" saturated, pivot to "retinal microvasculature fractal patterns"

## Output format

Literature Grounding (required)

**MANDATORY:** Explicit grounding in the literature review provided above.
- Cite specific papers/articles from the literature review that support this hypothesis
- Explain how findings from these papers inform or motivate the hypothesis
- Reference specific techniques, results, or gaps identified in the literature
- If multiple papers contributed, cite all relevant ones
- 2-4 sentences with explicit citations

## Guidelines

- Be honest about overlap - better to pivot than claim false novelty
- When refining, make specific changes (not vague improvements)
- When pivoting, stay related to original idea but find unexplored angle
- Use the novelty analyses to identify gaps and opportunities
- Prioritize hypotheses that address stated limitations or future work
- Keep hypothesis text concise and clear - use plain text with standard punctuation
- Avoid decorative Unicode characters or special formatting symbols in your output