# Hypothesis Validation Synthesis (with Tool Access)

You are validating draft hypotheses for novelty based on literature analysis. You have access to tools for searching additional papers and querying PDF content when needed.

## Research Goal
{{research_goal}}

## Literature Review and Analytical Rationale (pre-research done before any generation)

The following represents an analysis of relevant scientific literature:

#BEGIN LITERATURE REVIEW#
{{articles_with_reasoning}}

## Pre-Curated Papers (Available for Reference)

{{articles_metadata}}
#END LITERATURE REVIEW#

## Draft Hypotheses with Novelty Analyses

{{hypotheses_with_analyses}}

## Available Tools

You can use tools to search for additional papers or query PDF content when making validation decisions. This is especially useful when:
- Pivoting a hypothesis and need to verify the new direction isn't saturated
- Refining a hypothesis and need more context on differentiating factors
- The initial novelty analyses are inconclusive

**Tool Budget:** You have up to {{max_iterations}} tool calls available. Use them judiciously.

{{tool_instructions}}

## Your Task

For each draft hypothesis, decide whether to **approve**, **refine**, or **pivot** based on the novelty analyses provided. Use tools when needed to verify your decisions.

**IMPORTANT:** When creating the final literature grounding, use the papers mentioned in the draft's "literature sources" field as your primary citation basis. The draft identified those specific papers during gap analysis - cite them with proper (Author et al., year) format.

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
- Example: "retinal imaging" -> "hyperspectral retinal imaging for tau isoforms"

**Pivot (hypothesis is too saturated):**
- Many papers show "overlapping" assessment
- Existing work already covers the core idea
- Need to shift to related but unexplored angle
- **Use tools to search for papers** in the new direction to verify it's not also saturated
- Pivot based on gaps/future work identified in analyses
- Example: if "retinal imaging for AD" saturated, pivot to "retinal microvasculature fractal patterns"

## Output Format

**CRITICAL**: After using tools (if needed), respond with ONLY the raw JSON object. Do NOT wrap it in markdown code blocks (no ``` or ```json). Start your response directly with { and end with }.

**CRITICAL: Each hypothesis MUST include ALL FOUR components below:**

Output your hypotheses in JSON format. Provide a list of {{hypotheses_count}} hypotheses, each with:

### 1. Technical Hypothesis (required)
A densely formulated technical description following "We want to develop [X] to enable [Y]" format.
- Include specific technical details: algorithms, mechanisms, mathematical formulations, layer specifications, etc.
- Be precise about what will be developed and the technical approach
- 2-4 sentences maximum
- Use technical terminology appropriately

**Example:**
"We want to develop a 'Dynamic Velocity Sentinel'--which monitors the rate of change in latent activation directions across expanded early-to-mid layers (L < N/2) rather than static depths--to enable anticipatory SAE gating that triggers only when precursor signals cross a 'point of no return' for danger features. By integrating adversarial distillation to harden probes against injection attacks and relaxing layer constraints to capture sufficient signal fidelity, this approach ensures robust, pre-emptive interception of hazardous generations without incurring the cost of full-depth activation scanning."

### 2. Explanation (required)
A clear explanation of the approach for technical audiences (e.g., DARPA program managers, ML researchers), but in layman terms
- Core problem being addressed
- Explain why key mechanisms work
- How the components interact
- Practical advantages
- Avoid cartoonish analogies; use domain terminology appropriately

### 3. Literature Grounding (required)
**MANDATORY:** Explicit grounding in the literature review provided above with proper citations.

**CITATION FORMAT:** Use parenthetical (Author et al., year) format consistently. Place citations at the END of statements, not as narrative subjects.

**Correct (parenthetical):**
- "Plasma extracellular vesicles serve as early biomarkers (Malek-Ahmadi et al., 2026)."
- "Multiple studies have demonstrated this approach (Veron et al., 2026; Bazarbekov et al., 2026)."

**Requirements:**
- **CRITICAL: Use the draft's "literature sources" as your primary citation basis**
- The novelty analyses provide additional context about overlap/novelty, but the draft's literature sources should anchor your citations
- Cite specific papers/articles from the literature review that support this hypothesis
- If you searched for additional papers using tools, cite those as well
- 2-4 sentences with explicit citations

### 4. Practical Experiment (required)
A concrete, actionable experiment design to test the hypothesis. Structure with clear sections:

**Format:**
```
Objective: [1 sentence describing what you're testing]
Models: [Specific models/components needed]
Datasets: [Datasets and evaluation benchmarks]
Methodology: [Step-by-step experimental procedure]
Metrics: [Specific measurements and success criteria]
Validation: [What results would validate/invalidate the hypothesis]
```

## Guidelines

- Be honest about overlap - better to pivot than claim false novelty
- When refining, make specific changes (not vague improvements)
- When pivoting, **use tools to verify** the new direction isn't also saturated
- Use the novelty analyses to identify gaps and opportunities
- Prioritize hypotheses that address stated limitations or future work
- Keep hypothesis text concise and clear - use plain text with standard punctuation

## Output Format

**CRITICAL**: After using tools (if needed), respond with ONLY the raw JSON object. Do NOT wrap it in markdown code blocks (no ``` or ```json). Start your response directly with { and end with }.

**Output JSON structure:**

```json
{
  "hypotheses": [
    {
      "hypothesis": "Final dense technical hypothesis text, following 'We want to develop [X] to enable [Y]' format (2-3 sentences)",
      "explanation": "Step-by-step layman explanation breaking down the technical hypothesis (4-6 sentences)",
      "literature_grounding": "Explicit citations in (Author et al., year) format connecting specific findings to hypothesis. 2-4 sentences with citations.",
      "experiment": "Concrete experiment design with models, datasets, metrics, and validation criteria (4-6 sentences)",
      "novelty_validation": {
        "decision": "approved|refined|pivoted"
      }
    }
  ]
}
```

**Field requirements:**
- `hypothesis`: Technical formulation following "We want to develop [X] to enable [Y]" format (approved/refined/pivoted from draft)
- `explanation`: Clear explanation for technical audiences in layman terms
- `literature_grounding`: **CRITICAL - Use proper citations in (Author et al., year) format. Include papers from draft's literature_sources plus any papers found via tools.**
- `experiment`: Concrete, actionable experiment design to test the hypothesis
- `novelty_validation.decision`: Must be one of "approved", "refined", or "pivoted"

Output {{hypotheses_count}} validated hypotheses now. Output raw JSON with "hypotheses" array containing objects with all required fields above.
