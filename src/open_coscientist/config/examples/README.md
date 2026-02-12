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

See the [literature review tools](../../../../docs/literature_review_tools_configuration.md) documentation for a guide and schemas on this topic.