# Analyze Single Research Paper for Hypothesis Generation Opportunities

You are analyzing a biomedical research paper to identify opportunities for novel hypothesis generation.

## Research Goal
{{research_goal}}

## Paper Details
**Title:** {{title}}
**Authors:** {{authors}}
**Year:** {{year}}

## Paper Content
{{fulltext}}

---

## Your Task

Extract the following from this paper to identify opportunities for novel hypotheses:

### 1. Key Findings
Main contributions and results from this work. What did they discover or demonstrate?

### 2. Gaps Identified
What limitations or gaps did the authors explicitly mention? What questions remain unanswered?

### 3. Future Work Suggested
What did the authors suggest for future research? What next steps did they propose?

### 4. Methodology Limitations
What constraints or limitations existed in their methods? What couldn't they test or measure?

### 5. Unexplored Areas
Topics, variables, or approaches mentioned but not investigated in this study.

### 6. Relevance to Research Goal
How does this paper relate to the research goal? What context does it provide?

Focus on actionable insights that could inform novel hypothesis generation. Be specific and cite details from the paper.

## Response Format

Return a JSON object with this structure:

```json
{{
    "key_findings": "...",
    "gaps_identified": "...",
    "future_work": "...",
    "methodology_limitations": "...",
    "unexplored_areas": "...",
    "relevance": "..."
}}
```
