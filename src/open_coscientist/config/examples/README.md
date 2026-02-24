# Literature Review Tool Configuration Examples

This directory contains example YAML configurations for integrating external MCP servers and literature review tools with open-coscientist.

## Overview

Open-coscientist uses a **YAML-based configuration system** to decouple literature review tools from the core library. This allows you to:

- Bring your own MCP servers without modifying open-coscientist code
- Configure multiple literature sources (PubMed, arXiv, Google Scholar, etc.)
- Define custom response parsing, prompt instructions, and parameter mappings
- Mix and match tools from different MCP servers

The default configuration [../tools.yaml](../tools.yaml) provides a reference implementation using the bundled PubMed MCP server (See `mcp_server` at the top level of this repo).

## Example Configurations

### `arxiv_only.yaml`
**Purpose:** arXiv-only literature review
**Use case:** Research in AI/ML, physics, math, CS where arXiv has cutting-edge preprints
**Requirements:**
- MCP server with `search_arxiv` tool, configured for port 8889 on this example
- `read_pdf` tool for content extraction

**Features:**
- PDF content fetching via `content_tool: "read_pdf"`
- Query generation via MCP tool or LLM fallback

---

### `multi_source.yaml`
**Purpose:** Multi-source literature review (PubMed + arXiv + Google Scholar)
**Use case:** Comprehensive cross-disciplinary research
**Requirements:**
- PubMed MCP server on port 8888
- arXiv,Google Scholar MCP server on port 8889 (presumably has its own API KEYs requirements)

**Features:**
- `papers_per_query` per source (distribute papers across sources)
- Two-step PDF discovery for Google Scholar (`find_pdf_links` → `read_pdf`)
- Natural language query generation
- Cross-source deduplication

---

### `google_scholar.yaml`
**Purpose:** Google Scholar standalone
**Use case:** Broad academic search across all disciplines
**Requirements:**
- MCP server with `google_scholar_search` on port 8889
- `find_pdf_links` and `read_pdf` tools for PDF discovery

**Features:**
- Two-step PDF retrieval (landing page → PDF discovery → content fetch)
- Citation counts and venue metadata

---

### `pubmed_arxiv_same_server.yaml`
**Purpose:** PubMed + arXiv from a single MCP server
**Use case:** Biomedical + CS research from unified server
**Requirements:**
- Single MCP server on port 8888 with both PubMed and arXiv tools

**Features:**
- Simplified single-server configuration
- Multi-source deduplication

---

### `arxiv_and_google_scholar.yaml`
**Purpose:** arXiv + Google Scholar (no PubMed)
**Use case:** AI/ML research combined with broad academic coverage
**Requirements:**
- MCP server with arXiv and Google Scholar tools on port 8889
- SERPAPI_KEY for Google Scholar

**Features:**
- Replaces default PubMed config entirely (`merge_strategy: "replace"`)
- Two-step PDF discovery for Google Scholar
- Natural language query generation

---

### `arxiv_research_focused.yaml`
**Purpose:** arXiv with research-focused PDF analysis
**Use case:** When you want focused Q&A content instead of full text dumps
**Requirements:**
- MCP server with `search_arxiv` and `analyze_pdf_for_research` on port 8889

**Features:**
- **Research-focused content extraction** using `analyze_pdf_for_research` tool
- **`content_params` with runtime substitution** - passes research context to content tool
- Auto-generates questions based on research goal
- More token-efficient than full text extraction

**Key Configuration Pattern:**
```yaml
search_sources:
  - tool: "arxiv_search"
    content_tool: "analyze_pdf"
    content_url_field: "pdf_url"
    # Pass research context to the content tool
    content_params:
      research_goal: "{research_goal}"  # Substituted at runtime
      focus_areas:
        - "methodology"
        - "key findings"
```

---

## Content Parameters (`content_params`)

The `content_params` feature allows passing extra parameters to content tools. This is useful for tools that need context beyond just the URL:

### Supported Placeholders
- `{research_goal}` - The current research goal from workflow state
- `{focus_areas}` - List of focus areas (future: extracted from hypothesis categories)

### Example Usage
```yaml
workflows:
  literature_review:
    content_tool: "analyze_pdf_for_research"
    content_url_field: "pdf_url"
    content_params:
      research_goal: "{research_goal}"
      focus_areas:
        - "experimental methods"
        - "quantitative results"
```

This is particularly useful with the `analyze_pdf_for_research` tool, which generates questions dynamically based on the research context rather than extracting full text.

---

---

## INDRA CoGex Biomedical Domain Configurations

These four configs extend the default PubMed config with INDRA knowledge graph tools
(`merge_strategy: "extend"`). Each targets a distinct biomedical subdomain and audience,
and intentionally foregrounds different INDRA tools to showcase the full tool set.

**Requirements for all four:** PubMed MCP server on port 8888 with INDRA CoGex tools enabled.

| Config | Domain | Audience | Highlighted INDRA tools |
|---|---|---|---|
| `indra_cancer.yaml` | KRAS/NSCLC precision oncology | Oncology researchers | `query_mechanistic_statements`, `query_gene_codependents` (DepMap), `query_gene_disease_network` |
| `indra_alzheimers.yaml` | Alzheimer's drug repurposing | Neurodegeneration researchers | `query_mechanistic_statements`, `query_drug_info`, `query_pathways` |
| `indra_ibd.yaml` | IBD/Crohn's biologic resistance | Molecular gastroenterology researchers | `run_enrichment_analysis` (signed + discrete), `query_causal_subnetwork`, `query_pathways` (multi-gene) |
| `indra_hfpef.yaml` | HFpEF cardiac remodeling | Cardiologists / clinical trialists | `query_causal_subnetwork` (cardiometabolic mediators), `query_clinical_trials`, `query_drug_info` (repurposing) |

### `indra_ibd.yaml`
**Purpose:** IBD/Crohn's disease — biologic resistance mechanisms and upstream regulator discovery
**Audience:** Molecular biologists, pharmaceutical researchers in GI immunology
**Key differentiator:** `run_enrichment_analysis` in signed mode to identify upstream
transcriptional regulators from biologic responder/non-responder gene expression signatures.
`query_causal_subnetwork` to find indirect paths between risk genes (IL23R, NOD2) and
epithelial barrier disruption.

**Example research goal:**
> "What upstream transcriptional regulators explain the divergent immune gene expression
> signatures between biologic responders and non-responders in Crohn's disease, and what
> novel mechanistic targets do they suggest for next-generation IBD therapy?"

---

### `indra_hfpef.yaml`
**Purpose:** Heart failure with preserved ejection fraction (HFpEF) — connecting
cardiometabolic risk to cardiac remodeling
**Audience:** Cardiologists, heart failure specialists, clinical trialists
**Key differentiator:** `query_causal_subnetwork` to find the indirect molecular mediators
between cardiometabolic risk factors (obesity, T2D, hypertension) and adverse cardiac
remodeling — the central unanswered question in HFpEF. `query_clinical_trials` to map the
failed trial landscape. `query_drug_info` for cardiometabolic drug repurposing analysis.

**Example research goal:**
> "What shared molecular mediators connect cardiometabolic risk factors (obesity,
> hypertension, type 2 diabetes) to adverse cardiac remodeling in HFpEF, and which could
> serve as targets for novel pharmacological intervention in this patient population with
> no approved disease-modifying therapies?"

---

See the [literature review tools](../../../../docs/literature_review_tools_configuration.md) documentation for a guide and schemas on this topic.