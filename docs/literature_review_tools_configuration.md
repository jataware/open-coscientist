
## Overview

Open-coscientist uses a **YAML-based configuration system** to decouple literature review tools from the core library. This allows you to:

- Bring your own MCP servers without modifying open-coscientist code
- Configure multiple literature sources (PubMed, arXiv, Google Scholar, etc.)
- Define custom response parsing, prompt instructions, and parameter mappings
- Mix and match tools from different MCP servers

The default configuration (`../tools.yaml`) provides a reference implementation using the bundled PubMed MCP server (See mcp_server at the top leve of this repo).

## Example Configurations

See the [examples folder](../src/open_coscientist/config/examples/) (README and YAML files) for example configurations. They all use the _replace_ merge strategy—replacing completely the reference built-in `config/tools.yaml` in this project. See [Merge Strategies](#merge-strategies) for an overview of all merge strategies available.

## YAML Configuration Schema

### Top-Level Structure

```yaml
version: "1.0"

servers:
  server_id:
    url: "http://localhost:8888/mcp"
    transport: "streamable_http"
    enabled: true

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

settings:
  auto_discover: true
  merge_strategy: "replace"
  allow_disable_builtins: true
```

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
| `source_type` | string | Yes | `"academic"`, `"preprint"`, `"pubmed"`, `"knowledge_graph"` |
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
        # content_tool: "read_pdf"       # Optional: specify content tool
        # content_url_field: "pdf_url"   # Field containing content URL

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

    # Additional tools
    read_tools:
      - "read_pdf"
      - "query_pdf"
    utility_tools:
      - "find_pdf_links"
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

---

### Source Type and Query Generation

The `source_type` field determines query generation strategy:

| Source Type | Query Format | Use Case |
|-------------|--------------|----------|
| `"pubmed"` | Boolean (AND/OR/NOT) | PubMed-specific syntax |
| `"academic"` | Natural language | General academic search |
| `"preprint"` | Natural language | arXiv, bioRxiv, etc. |
| `"knowledge_graph"` | Gene/protein names | INDRA, STRING, etc. |

**LLM-based query generation** (when `query_generation_tool: null`):
- Detects source types from enabled sources
- Selects appropriate prompt template
- Generates source-appropriate queries

**MCP-based query generation** (when `query_generation_tool` specified):
- Calls MCP tool with `query_format` parameter
- Falls back to LLM if tool unavailable

---

## Using These Configurations

### Method 1: Pass to HypothesisGenerator

```python
from open_coscientist import HypothesisGenerator

generator = HypothesisGenerator(
    research_goal="Your research question",
    tools_config="path/to/multi_source.yaml"
)

result = generator.run()
```

### Method 2: Copy to User Config Directory

```bash
cp multi_source.yaml ~/.coscientist/tools.yaml
```

The registry automatically loads from `~/.coscientist/tools.yaml` if present.

### Method 3: Modify and Merge

Create a custom config that overrides specific tools:

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

Control how user configs interact with built-in `tools.yaml`:

| Strategy | Behavior |
|----------|----------|
| `"replace"` | User config completely replaces built-in config |
| `"extend"` | User config adds to built-in config (tools are merged) |
| `"override"` | User tools override built-in tools with same ID |

Set in `settings.merge_strategy`.

---

## Limitations and Future Work

### Current Limitations

1. **Single query set for all sources:** Multi-source configs use the same queries for all sources. If sources are mixed and ran on the same literature-review/query generation process, some may yield no results for a source. Alternatives include running the hypothesis generation process twice- one per source/mcp server. Or, extending the project to better support per-source query generation in the same run.

.2 MCP caching is assumed to occur on the mcp server side.

## Getting Help

- **Schema validation errors:** Check field names and types against this README
- **MCP connection errors:** Verify `url` and `enabled` in server configs
- **Missing tools:** Check MCP server logs - tool must be registered
- **Empty results:** Check `response_format.field_mapping` matches MCP response structure