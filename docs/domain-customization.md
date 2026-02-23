# Domain Customization

Open Coscientist is domain-agnostic by design. The default configuration targets biomedical research (PubMed), but the system can be adapted to any research domain — cybersecurity, materials science, climate research, bioinformatics, or subdomains like Alzheimer's drug repurposing — through a YAML configuration file. No changes to source code or prompts are needed.

A domain config controls:

- **Which MCP servers and literature sources to use** (arXiv, Google Scholar, NVD, INDRA, etc.)
- **Prompt guidance** injected into hypothesis generation, review, and evolution
- **Post-generation enrichments** that attach domain-specific data to each hypothesis (e.g., related CVEs, knowledge graph entries)

See [Literature Review Tools Configuration](literature_review_tools_configuration.md) for the full YAML schema reference.

---

## How It Works

### 1. Choose Your Sources

Point to an MCP server and define which tools it exposes:

```yaml
servers:
  my_server:
    url: "${MY_MCP_URL:-http://localhost:8889/mcp}"
    transport: "streamable_http"
    enabled: true

tools:
  search_tools:
    arxiv_search:
      server: "my_server"
      mcp_tool_name: "search_arxiv"
      source_type: "preprint"
      # ...
```

### 2. Add Domain Prompt Guidance

The `prompts` section injects text into the Generate, Review, and Evolve nodes without modifying any code:

```yaml
prompts:
  domain_context: |
    You are a cybersecurity researcher. "Hypothesis" means a threat hypothesis —
    a novel attack technique or adversarial capability.

  generation_guidance: |
    Generate hypotheses spanning: novel exploitation, evasion techniques,
    AI-augmented attacks, and supply chain compromise.

  review_guidance: |
    Prioritize: operational feasibility, novelty over existing TTPs,
    and defensive value (purple team utility).
```

### 3. Add Enrichments (Optional)

Enrichments call a tool once per hypothesis after generation and attach results to `hypothesis["enrichments"]`. Useful for domain-specific data that complements the literature:

```yaml
enrichments:
  - tool: "nvd_cve_search"
    input_field: "text"
    output_key: "related_cves"
    results_path: "results"
    enabled: true
    max_results: 5
```

### 4. Set Merge Strategy

Use `merge_strategy: "replace"` to fully replace the default PubMed config, or `"extend"` to add sources alongside it:

```yaml
settings:
  merge_strategy: "replace"
```

---

## Example Domains

The following example configurations are included in [`src/open_coscientist/config/examples/`](../src/open_coscientist/config/examples/):

### Biomedical — Alzheimer's Drug Repurposing (`indra_alzheimers.yaml`)

Extends the default PubMed config with INDRA CoGex knowledge graph tools. INDRA provides curated causal statements from literature (e.g., drug → pathway → target relationships), supplementing PubMed full-text search with structured mechanistic knowledge.

**Sources:** PubMed (default) + INDRA CoGex (knowledge graph)
**Enrichments:** INDRA pathway statements per hypothesis
**Use case:** Drug repurposing, neuroinflammation, biomarker identification

```yaml
# Extends default config — PubMed still runs, INDRA adds mechanistic context
settings:
  merge_strategy: "extend"
```

### Biomedical — Cancer (`indra_cancer.yaml`)

Similar to the Alzheimer's config, adapted for oncology hypothesis generation with cancer-specific prompt guidance and INDRA integration.

**Sources:** PubMed + INDRA CoGex
**Use case:** Cancer pathway hypotheses, drug combinations, resistance mechanisms

### Cybersecurity (`cybersecurity_hydra.yaml`)

Replaces the default PubMed config entirely. Uses arXiv for academic security research and Google Scholar for conference papers (USENIX Security, CCS, IEEE S&P, NDSS). NVD CVE search is added both as a literature source and as a post-generation enrichment that attaches related CVEs to each hypothesis.

**Sources:** arXiv + Google Scholar + NVD CVE
**Enrichments:** Related CVEs per hypothesis
**Use case:** Threat hypothesis generation, vulnerability research, red team planning

```yaml
prompts:
  domain_context: |
    "Hypothesis" means a threat hypothesis: a novel attack technique,
    exploitation method, or adversarial capability.
  review_guidance: |
    Prioritize: operational feasibility, novelty over existing TTPs, evasion
    potential, and defensive value (purple team utility).
```

### Multi-source Academic (`multiple_sources.yaml`, `arxiv_and_google_scholar.yaml`)

Configurations for cross-disciplinary research without domain-specific guidance. Useful for AI/ML, physics, mathematics, or broad academic topics where PubMed is not appropriate.

**Sources:** arXiv + Google Scholar
**Use case:** AI/ML research, computer science, interdisciplinary topics

---

## Using a Custom Config

Pass the YAML path when creating `HypothesisGenerator`:

```python
import asyncio
from open_coscientist import HypothesisGenerator

async def main():
    generator = HypothesisGenerator(
        model_name="gemini/gemini-2.5-flash",
        tools_config="path/to/my_domain.yaml"
    )

    async for node_name, state in generator.generate_hypotheses(
        research_goal="Your domain-specific research question",
        stream=True
    ):
        print(f"Completed: {node_name}")
        if node_name == "rank":
            for h in state["hypotheses"]:
                print(h["text"])
                print(h.get("enrichments", {}))  # domain-specific enrichment data

asyncio.run(main())
```

Alternatively, place the config at `~/.coscientist/tools.yaml` and it will be loaded automatically.

---

## Writing a Config for a New Domain

1. **Identify your literature sources** — what databases or APIs exist for your domain? Any MCP-compatible server can be integrated.
2. **Define prompt guidance** — what terminology does your domain use? What makes a hypothesis "good" in this domain? What should the experiment section look like?
3. **Consider enrichments** — is there structured domain data (CVEs, pathway databases, patent records) that should be attached per hypothesis?
4. **Pick a merge strategy** — `replace` if you're fully replacing PubMed, `extend` if you want to add to it.

Refer to the [Literature Review Tools Configuration](literature_review_tools_configuration.md) for the full YAML schema, and the [examples README](../src/open_coscientist/config/examples/README.md) for annotated examples.
