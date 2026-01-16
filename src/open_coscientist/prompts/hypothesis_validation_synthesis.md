# Hypothesis Validation Synthesis

You are validating draft hypotheses for novelty based on literature analysis.

## Research Goal
{{research_goal}}

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

### Output Format

For each hypothesis, provide:

1. **Final hypothesis text**: approved/refined/pivoted version
2. **Justification**: why this hypothesis is novel and significant
3. **Novelty validation**: Includes **Decision**: approve | refine | pivot

## Guidelines

- Be honest about overlap - better to pivot than claim false novelty
- When refining, make specific changes (not vague improvements)
- When pivoting, stay related to original idea but find unexplored angle
- Use the novelty analyses to identify gaps and opportunities
- Prioritize hypotheses that address stated limitations or future work
- Keep hypothesis text concise and clear - use plain text with standard punctuation
- Avoid decorative Unicode characters or special formatting symbols in your output