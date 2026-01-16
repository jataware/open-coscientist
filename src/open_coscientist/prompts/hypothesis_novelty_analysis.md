# Analyze Paper for Hypothesis Novelty Assessment

You are analyzing a research paper to assess whether a proposed hypothesis is novel compared to existing work.

## Hypothesis to Validate
{{hypothesis_text}}

## Paper Details
**Title:** {{title}}
**Authors:** {{authors}}
**Year:** {{year}}

## Paper Content
{{fulltext}}

---

## Your Task

Analyze this paper to determine how it relates to the proposed hypothesis and whether the hypothesis remains novel.

### Analysis Areas

**1. Methods and Approaches**
What specific methods, techniques, or approaches does this paper use? Are they similar to or different from what the hypothesis proposes?

**2. Populations and Scope**
What populations, samples, or contexts does this paper study? Does it cover the same scope as the hypothesis?

**3. Mechanisms and Targets**
What biological mechanisms, targets, or pathways does this paper investigate? Does it address the same mechanisms as the hypothesis?

**4. Findings and Conclusions**
What are the main findings? Do they already answer what the hypothesis proposes to investigate?

**5. Stated Limitations**
What limitations or gaps do the authors explicitly mention? Could the hypothesis address these?

**6. Suggested Future Work**
What future directions do the authors suggest? Does the hypothesis align with or go beyond these suggestions?

**7. Novelty Assessment**
Based on the above, how does the hypothesis compare to this paper?
- **Overlapping**: Hypothesis is similar or already covered.
- **Complementary**: Hypothesis extends this work in a new direction.
- **Orthogonal**: Hypothesis is different (different method/population/mechanism).
- **Addresses Gaps**: Hypothesis directly addresses limitations mentioned.

## Response Format

Return a JSON object with this structure:

```json
{{
    "methods_used": "What methods/techniques this paper employs",
    "populations_studied": "What populations/contexts are covered",
    "mechanisms_investigated": "What mechanisms/targets are studied",
    "key_findings": "Main findings relevant to the hypothesis",
    "stated_limitations": "Limitations or gaps the authors mention",
    "future_work_suggested": "Future directions the authors propose",
    "novelty_assessment": "overlapping | complementary | orthogonal | addresses_gaps",
    "overlap_explanation": "Detailed explanation of how hypothesis compares to this paper"
}}
```

**Text formatting guidelines:**
- Use standard scientific notation and symbols (Greek letters like τ, β, α, mathematical operators like ≥, ≤, ±)
- Do NOT use LaTeX commands (e.g., use 'τ' not '\tau', use '≥' not '\geq')
- Avoid decorative formatting, repeated special characters, or fancy text styling
- Prefer concise plain text when it communicates the idea equally well
