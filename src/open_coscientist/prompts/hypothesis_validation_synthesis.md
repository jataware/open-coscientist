# Hypothesis Validation Synthesis

You are validating draft hypotheses for novelty based on literature analysis.

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

## Your Task

For each draft hypothesis, decide whether to **approve**, **refine**, or **pivot** based on the novelty analyses provided.

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
- Example: "retinal imaging" → "hyperspectral retinal imaging for tau isoforms"

**Pivot (hypothesis is too saturated):**
- Many papers show "overlapping" assessment
- Existing work already covers the core idea
- Need to shift to related but unexplored angle
- Pivot based on gaps/future work identified in analyses
- Example: if "retinal imaging for AD" saturated, pivot to "retinal microvasculature fractal patterns"

## Output format

**CRITICAL: Each hypothesis MUST include ALL FOUR components below:**

Output your hypotheses in JSON format. Provide a list of {{hypotheses_count}} hypotheses, each with:

### 1. Technical Hypothesis (required)
A densely formulated technical description following "We want to develop [X] to enable [Y]" format.
- Include specific technical details: algorithms, mechanisms, mathematical formulations, layer specifications, etc.
- Be precise about what will be developed and the technical approach
- 2-4 sentences maximum
- Use technical terminology appropriately

**Example:**
"We want to develop a 'Dynamic Velocity Sentinel'—which monitors the rate of change in latent activation directions across expanded early-to-mid layers (L < N/2) rather than static depths—to enable anticipatory SAE gating that triggers only when precursor signals cross a 'point of no return' for danger features. By integrating adversarial distillation to harden probes against injection attacks and relaxing layer constraints to capture sufficient signal fidelity, this approach ensures robust, pre-emptive interception of hazardous generations without incurring the cost of full-depth activation scanning."

### 2. Explanation (required)
A clear explanation of the approach for technical audiences (e.g., DARPA program managers, ML researchers), but in layman terms
- Core problem being addressed
- Explain why key mechanisms work
- How the components interact
- Practical advantages
- Avoid cartoonish analogies; use domain terminology appropriately

**Example:**
"This approach addresses the computational bottleneck of full-depth activation monitoring by focusing on early-to-mid transformer layers (L < N/2) where precursor signals for harmful content first emerge. Rather than analyzing static activation magnitudes, the technique tracks velocity—the rate of change in latent activation directions—which provides earlier detection of trajectories toward dangerous outputs. The monitoring system employs sparse autoencoders to identify interpretable danger features, with dynamic gating that triggers intervention only when activation trajectories cross a learned threshold indicating irreversible progression toward harmful generation. To ensure robustness against adversarial manipulation, the detection probes are hardened via adversarial distillation, preventing attackers from injecting misleading signals that could disable safety monitoring. This architecture achieves anticipatory interception while maintaining inference efficiency by avoiding full-depth scanning."

### 3. Literature Grounding (required)
**MANDATORY:** Explicit grounding in the literature review provided above with proper citations.

**CITATION FORMAT:** Use parenthetical (Author et al., year) format consistently. Place citations at the END of statements, not as narrative subjects.

**Correct (parenthetical):**
- "Plasma extracellular vesicles serve as early biomarkers (Malek-Ahmadi et al., 2026)."
- "Multiple studies have demonstrated this approach (Verón et al., 2026; Bazarbekov et al., 2026)."

**INCORRECT (narrative):**
- "Malek-Ahmadi et al. (2026) showed that plasma extracellular vesicles..."
- "Verón et al. (2026) demonstrated..."

**Requirements:**
- **CRITICAL: Use the draft's "literature sources" as your primary citation basis** - the draft identified specific papers during gap analysis, cite those papers in your literature grounding
- The novelty analyses provide additional context about overlap/novelty, but the draft's literature sources should anchor your citations
- Cite specific papers/articles from the literature review that support this hypothesis
- Explain how findings from these papers inform or motivate the hypothesis
- Reference specific techniques, results, or gaps identified in the literature
- If multiple papers contributed, cite all relevant ones
- 2-4 sentences with explicit citations
- **Connect back to the gap reasoning** - explain how the papers cited relate to the specific gap the draft identified

**Example (correct parenthetical style):**
"This approach builds on recent work in sparse autoencoder (SAE) analysis and circuit tracing methodologies (Templeton et al., 2024; Conmy et al., 2023). The 'velocity' monitoring concept addresses a gap where current methods focus on static activation analysis rather than temporal dynamics (Marks et al., 2024). The adversarial hardening component is motivated by research showing that interpretability tools themselves can be exploited (Casper et al., 2024), necessitating robust monitoring approaches."

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

**Example:**
"Objective: Demonstrate that dynamic velocity monitoring in early layers achieves comparable safety detection to full-depth scanning with reduced computational cost.

Models: GPT-2 Medium (target LLM), pre-trained SAE from TransformerLens SAELens library applied to layers 1-6, baseline full-depth monitor on layers 1-24.

Datasets: AdvBench harmful prompts dataset (500 adversarial examples), Anthropic HH-RLHF benign prompts (1000 examples for false positive testing), custom red-team dataset of 100 novel attack vectors.

Methodology: (1) Implement velocity tracking by computing gradient of activation directions across consecutive forward passes in layers 1-6. (2) Train threshold detector on 80% of AdvBench to identify 'point of no return' trajectories. (3) Compare detection timing and accuracy against full-depth baseline. (4) Measure computational overhead (FLOPs, latency) for both approaches.

Metrics: Detection accuracy (precision/recall/F1), detection timing (layers until trigger), false positive rate on benign prompts, computational overhead (% of baseline inference cost), robustness to adversarial probe attacks.

Validation: Success requires >90% detection rate, <5% false positive rate, >50% reduction in computational cost vs. full-depth scanning, and maintained performance under adversarial probe attacks. Single A100 GPU, ~48 hours runtime."

## Guidelines

- Be honest about overlap - better to pivot than claim false novelty
- When refining, make specific changes (not vague improvements)
- When pivoting, stay related to original idea but find unexplored angle
- Use the novelty analyses to identify gaps and opportunities
- Prioritize hypotheses that address stated limitations or future work
- Keep hypothesis text concise and clear - use plain text with standard punctuation
- Avoid decorative Unicode characters or special formatting symbols in your output