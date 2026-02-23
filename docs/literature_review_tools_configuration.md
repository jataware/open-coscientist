# Literature Review Tools Configuration

## Overview

Open Coscientist uses a **YAML-based configuration system** to decouple literature review tools from the core library. This allows you to:

- Bring your own MCP servers without modifying open-coscientist code
- Configure multiple literature sources (PubMed, arXiv, Google Scholar, etc.)
- Define custom response parsing, prompt instructions, and parameter mappings
- Mix and match tools from different MCP servers
- Inject domain-specific prompt guidance without touching source code

The default configuration (`src/open_coscientist/config/tools.yaml`) provides a reference implementation using the bundled PubMed MCP server (see `mcp_server/` at the top level of this repo).

For how to use these configs to adapt the system to a specific domain, see [Domain Customization](domain-customization.md).

## Example Configurations

See the [examples folder](../src/open_coscientist/config/examples/) (README and YAML files) for example configurations. See [Merge Strategies](#merge-strategies) for an overview of how user configs interact with the built-in defaults.

## YAML Configuration Schema

### Top-Level Structure

```yaml
version: "1.0"

servers:
  server_id:
    url: "http://localhost:8888/mcp"
    transport: "streamable_http"
    enabled: true

prompts:
  domain_context: |
    # Optional: injected into generation, review, and evolution prompts
  generation_guidance: |
    # Optional: additional instructions for the Generate node
  review_guidance: |
    # Optional: additional criteria for the Review node
  evolution_guidance: |
    # Optional: additional priorities for the Evolve node

tools:
  search_tools:
    tool_id:
      # Tool configuration (see below)
  read_tools:
    # Content retrieval tools
  utility_tools:
    # Helper tools (PDF discovery, availability checks)

workflows:
  literature_review:
    # Workflow configuration (see below)
  draft_generation:
    # Tools available to the Generate node in tool-calling mode
  validation:
    # Tools available for novelty validation

enrichments:
  # Post-generation per-hypothesis tool calls (see below)

settings:
  auto_discover: true
  merge_strategy: "replace"
  allow_disable_builtins: true
```

---

### Server Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | MCP server URL (supports `${ENV_VAR:-default}`) |
| `transport` | string | Yes | Always `"streamable_http"` |
| `enabled` | boolean | Yes | Enable/disable this server |

**Example:**
```yaml
servers:
  arxiv_server:
    url: "${ARXIV_MCP_SERVER_URL:-http://localhost:8889/mcp}"
    transport: "streamable_http"
    enabled: true
```

---

### Prompt Customization

The `prompts` section injects domain-specific text into workflow prompts without requiring any code changes. All fields are optional.

| Field | Injected Into |
|-------|--------------|
| `domain_context` | Supervisor, Generate, Review, Evolve nodes |
| `generation_guidance` | Generate node |
| `review_guidance` | Review node |
| `evolution_guidance` | Evolve node |

**Example (cybersecurity domain):**
```yaml
prompts:
  domain_context: |
    ## Domain: Offensive Cybersecurity Research

    You are a cybersecurity research scientist. "Hypothesis" means a threat
    hypothesis — a novel attack technique or adversarial capability.

  generation_guidance: |
    ## Attack Categories to Consider
    Generate hypotheses spanning: novel exploitation, evasion techniques,
    AI-augmented attacks, supply chain compromise, and post-exploitation.

  review_guidance: |
    ## Cybersecurity Review Criteria
    Prioritize: operational feasibility, novelty over existing TTPs,
    impact potential, evasion potential, and defensive value.
```

See the [examples folder](../src/open_coscientist/config/examples/) for complete domain-specific configurations.

---

### Tool Configuration

Tools are organized into categories: `search_tools`, `read_tools`, `utility_tools`.

#### Search Tool Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `server` | string | Yes | Server ID from `servers` section |
| `mcp_tool_name` | string | Yes | Actual tool name in MCP server |
| `display_name` | string | Yes | Human-readable name |
| `description` | string | Yes | Tool description |
| `category` | string | Yes | `"search"` or `"search_with_content"` |
| `source_type` | string | Yes | See [Source Types](#source-type-and-query-generation) |
| `enabled` | boolean | Yes | Enable/disable tool |
| `response_format` | object | Yes | How to parse MCP response (see below) |
| `parameter_mapping` | object | No | Map canonical params to tool params |
| `prompt_snippet` | string | No | Instructions for LLM agents |
| `parameters` | object | No | Tool parameter definitions |

#### Response Format

Defines how to parse MCP tool responses into `Article` objects.

```yaml
response_format:
  type: "json"                    # "json" or "boolean_string"
  results_path: "."              # JSONPath to results array ("." for root)
  is_dict: true                  # true if results are {key: value}, false if [...]
  field_mapping:
    title: "title"               # Direct field
    url: "@url_from_key"         # Special: construct URL from dict key
    authors: "authors"
    year: "date_revised|split:/|index:0|int"  # Transform chain
    abstract: "abstract"
    content: "fulltext"
    source_id: "@key"            # Special: use dict key as ID
    source: "'pubmed'"           # Static value (quoted)
    venue: "publication"
    pdf_links: "pdf_url|wrap_list"  # Wrap single value in list
```

**Transform chains:**
- `split:/` - split on `/`
- `index:0` - take first element
- `int` - convert to integer
- `wrap_list` - wrap in list
- `@key` - use dict key
- `@url_from_key` - construct URL from key
- `'static'` - literal value (must be quoted)

#### Parameter Mapping

Maps canonical parameter names to tool-specific names:

```yaml
parameter_mapping:
  query: "query"              # canonical → tool param
  max_papers: "max_results"   # different name
  recency_years: null         # not supported by this tool
  slug: null                  # ignore
```

**Canonical parameters:**
- `query` - search query string
- `max_papers` - max results to return
- `recency_years` - filter to recent papers
- `slug` - research corpus identifier
- `run_id` - run tracking ID

---

### Workflow Configuration

Defines tool usage for specific workflow phases.

```yaml
workflows:
  literature_review:
    # OPTION 1: Single-source mode
    primary_search: "pubmed_fulltext"

    # OPTION 2: Multi-source mode
    search_sources:
      - tool: "pubmed_fulltext"
        papers_per_query: 4
        enabled: true

      - tool: "google_scholar_search"
        papers_per_query: 2
        enabled: true
        # Two-step PDF retrieval
        pdf_discovery_tool: "find_pdf_links"
        pdf_discovery_url_field: "url"
        content_tool: "read_pdf"
        content_url_field: "pdf_url"

    # Multi-source settings
    multi_source_strategy: "parallel"
    deduplicate_across_sources: true

    # Availability check
    availability_check: "check_pubmed"  # or null to skip

    # Query generation
    query_generation_tool: "generate_queries"  # or null for LLM-based
    query_format: "natural_language"  # "natural_language" or "boolean"

    # Content retrieval (fallback)
    content_tool: "read_pdf"
    content_url_field: "pdf_url"

    # Additional tools available to the lit review agent
    read_tools:
      - "read_pdf"
      - "query_pdf"
    utility_tools:
      - "find_pdf_links"

  # Tools available to the Generate node in tool-calling mode (Mode 3)
  draft_generation:
    search_tools:
      - "arxiv_search"
      - "nvd_cve_search"
    read_tools:
      - "read_pdf"

  # Tools available for novelty validation
  validation:
    search_tools:
      - "arxiv_search"
    read_tools:
      - "read_pdf"
```

#### Multi-Source Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Tool ID from `tools` section |
| `papers_per_query` | integer | Papers to fetch per query from this source |
| `enabled` | boolean | Enable/disable this source |
| `content_tool` | string | Tool for fetching paper content (optional) |
| `content_url_field` | string | Field containing URL for content tool (optional) |
| `pdf_discovery_tool` | string | Tool for finding PDF URLs from landing pages (optional) |
| `pdf_discovery_url_field` | string | Field containing landing page URL (optional) |
| `content_params` | object | Extra parameters passed to content tool (optional); supports `{research_goal}` placeholder |

**Content retrieval strategies:**

1. **Direct fulltext** (PubMed):
   ```yaml
   - tool: "pubmed_fulltext"
     # No content_tool needed - returns fulltext directly
   ```

2. **PDF URL provided** (arXiv):
   ```yaml
   - tool: "arxiv_search"
     content_tool: "read_pdf"
     content_url_field: "pdf_url"
   ```

3. **Two-step discovery** (Google Scholar):
   ```yaml
   - tool: "google_scholar_search"
     pdf_discovery_tool: "find_pdf_links"  # Step 1: landing page → PDF URL
     pdf_discovery_url_field: "url"
     content_tool: "read_pdf"              # Step 2: PDF URL → content
     content_url_field: "pdf_url"
   ```

4. **Research-focused content extraction** (with context params):
   ```yaml
   - tool: "arxiv_search"
     content_tool: "analyze_pdf_for_research"
     content_url_field: "pdf_url"
     content_params:
       research_goal: "{research_goal}"   # substituted at runtime
       focus_areas:
         - "methodology"
         - "key findings"
   ```

---

### Source Type and Query Generation

The `source_type` field determines query generation strategy:

| Source Type | Query Format | Use Case |
|-------------|--------------|----------|
| `"pubmed"` | Boolean (AND/OR/NOT) | PubMed-specific syntax |
| `"academic"` | Natural language | General academic search (Google Scholar) |
| `"preprint"` | Natural language | arXiv, bioRxiv, etc. |
| `"knowledge_graph"` | Gene/protein names | INDRA, STRING, etc. |
| `"vulnerability_database"` | Topic keywords | NVD/CVE databases |

**LLM-based query generation** (when `query_generation_tool: null`):
- Detects source types from enabled sources
- Selects appropriate prompt template
- Generates source-appropriate queries

**MCP-based query generation** (when `query_generation_tool` specified):
- Calls MCP tool with `query_format` parameter
- Falls back to LLM if tool unavailable

---

### Enrichments

Post-generation enrichments call a tool once per hypothesis and attach the results to `hypothesis.enrichments`. This is useful for domain-specific data that augments the output (e.g., related CVEs in cybersecurity, or gene interaction data in biomedicine).

```yaml
enrichments:
  - tool: "nvd_cve_search"
    input_field: "text"          # Hypothesis field used as query input
    output_key: "related_cves"   # Key under hypothesis.enrichments
    results_path: "results"      # JSONPath into tool response
    enabled: true
    max_results: 5
```

Each entry in `enrichments` produces a key under `hypothesis["enrichments"]`. Multiple enrichment tools can be configured.

---

## Using These Configurations

### Method 1: Pass to HypothesisGenerator

```python
import asyncio
from open_coscientist import HypothesisGenerator

async def main():
    generator = HypothesisGenerator(
        model_name="gemini/gemini-2.5-flash",
        tools_config="path/to/my_config.yaml"
    )

    async for node_name, state in generator.generate_hypotheses(
        research_goal="Your research question",
        stream=True
    ):
        print(f"Completed: {node_name}")

asyncio.run(main())
```

### Method 2: Copy to User Config Directory

```bash
cp my_config.yaml ~/.coscientist/tools.yaml
```

The registry automatically loads from `~/.coscientist/tools.yaml` if present.

### Method 3: Modify and Merge

Create a custom config that extends or overrides specific tools:

```yaml
version: "1.0"

settings:
  merge_strategy: "extend"  # Extend built-in config

tools:
  search_tools:
    my_custom_tool:
      # Your custom tool config
```

---

## Merge Strategies

Control how user configs interact with the built-in `tools.yaml`:

| Strategy | Behavior |
|----------|----------|
| `"replace"` | User config completely replaces built-in config |
| `"extend"` | User config adds to built-in config (tools are merged) |
| `"override"` | User tools override built-in tools with same ID |

Set in `settings.merge_strategy`.

---

## Limitations and Future Work

1. **Single query set for all sources:** Multi-source configs use the same queries for all sources. If sources are mixed in the same run, some may yield no results for certain source types. Alternatives include running hypothesis generation once per source, or extending the project to support per-source query generation in the same run.

2. **MCP caching:** Caching of MCP tool responses is assumed to occur on the MCP server side.

## Getting Help

- **Schema validation errors:** Check field names and types against this document
- **MCP connection errors:** Verify `url` and `enabled` in server configs
- **Missing tools:** Check MCP server logs — tool must be registered
- **Empty results:** Check `response_format.field_mapping` matches MCP response structure
