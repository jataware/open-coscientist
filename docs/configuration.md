# Configuration Guide

Complete guide to configuring Open Coscientist for your needs.

## Basic Configuration

```python
from open_coscientist import HypothesisGenerator

generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",   # Default; Any LiteLLM-supported model
    max_iterations=1,                       # Number of refinement cycles
    initial_hypotheses_count=5,             # Initial pool size
    evolution_max_count=3,                  # How many to evolve and keep
    enable_cache=True,                      # LLM response caching
    cache_dir=".coscientist_cache",         # Cache location (relative to CWD)
)
```

See constants.py for other defaults.

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_name` | `"gemini/gemini-2.5-flash"` | LLM model in LiteLLM format (e.g., `"claude-3-5-sonnet-20241022"`, `"gpt-4"`, `"gemini/gemini-2.5-flash"`) |
| `max_iterations` | `1` | Number of refinement cycles (0 = no evolution/meta-review phase) |
| `initial_hypotheses_count` | `5` | Initial hypothesis pool size |
| `evolution_max_count` | `3` | Number of top hypotheses to evolve in each iteration |
| `enable_cache` | `True` | Enable LLM response caching for faster iteration |
| `cache_dir` | `".coscientist_cache"` | Cache directory (relative or absolute path) |

## Model Selection

Open Coscientist uses [LiteLLM](https://docs.litellm.ai/docs/providers), which supports 100+ LLM providers:

### OpenAI

```python
# Set API key
export OPENAI_API_KEY="your-key-here"

# Use in code
generator = HypothesisGenerator(model_name="gpt-4o")
```

### Anthropic

```python
# Set API key
export ANTHROPIC_API_KEY="your-key-here"

# Use in code
generator = HypothesisGenerator(model_name="claude-4-5-sonnet")
```

### Google Gemini

```python
# Set API key
export GEMINI_API_KEY="your-key-here"

# Use in code
generator = HypothesisGenerator(model_name="gemini/gemini-2.5-flash")
```

### Azure, AWS Bedrock, Cohere

See [LiteLLM provider documentation](https://docs.litellm.ai/docs/providers) for configuration details.

## Runtime Options

The `generate_hypotheses()` method accepts an `opts` dictionary for runtime configuration:

```python
# Non-streaming
result = await generator.generate_hypotheses(
    research_goal="Your research question",
    stream=False,  # Will have to wait with no feedback, sometimes >10 minutes, if no cache and no logging enabled
    opts={
        # Literature review control
        "enable_literature_review_node": True,
        "enable_tool_calling_generation": False,
    }
)

# Streaming
async for node_name, state in generator.generate_hypotheses(
    research_goal="Your research question",
    stream=True,
    opts={...}
):
    print(f"Completed: {node_name}")
```

### Available Runtime Options

| Option | Default | Description |
|--------|---------|-------------|
| `enable_literature_review_node` | `True` (if MCP available) | Enable/disable literature review node |
| `enable_tool_calling_generation` | `False` | Allow Generate node to use MCP tools (requires literature review) |

See [MCP Integration](mcp-integration.md) for details on literature review modes.

## Caching

LLM caching dramatically speeds up development and testing by reusing identical LLM calls.

### Cache Management

```python
from open_coscientist import clear_cache, get_cache_stats

# Clear all cached responses
cleared = clear_cache()
print(f"Cleared {cleared} responses")

# Check cache statistics
stats = get_cache_stats()
print(f"Cache: {stats['cache_files']} files, {stats['total_size_mb']:.2f} MB")
```

### Environment Variables

#### Caching

```bash
# Enable/disable caching
export COSCIENTIST_CACHE_ENABLED=true

# Custom cache directory
export COSCIENTIST_CACHE_DIR=".cache"
```

#### Literature Review (PubMed)

Literature review uses a separate MCP server that runs in its own process (Python 3.12+). Configure the MCP server by editing `mcp_server/.env`:

```bash
# Required for PubMed access
ENTREZ_EMAIL=your_email@example.com

# Optional: higher rate limits
ENTREZ_API_KEY=your_ncbi_api_key

# Optional: literature review cache directory
COSCIENTIST_LIT_REVIEW_DIR=./cache/literature_review
```

**Important Notes**:
- The MCP server runs separately with its own environment - set API keys in `mcp_server/.env`, not in the main open-coscientist environment
- Without `ENTREZ_EMAIL`, the literature review node will be skipped and hypothesis generation will use standard mode (without literature analysis)

### Cache Behavior

- **Default location**: `.coscientist_cache/` relative to current working directory
- **Cache key includes**: prompt, model name, temperature, max_tokens
- **Benefits**: faster iteration during development, significant cost savings
- **Safe to delete**: Cache directory can be deleted at any time

## Constants and Internal Parameters

Most users won't need to modify these, but they're centralized in `src/open_coscientist/constants.py`:

### Elo Rating Parameters

```python
INITIAL_ELO_RATING = 1200  # Starting Elo rating for all hypotheses
ELO_K_FACTOR = 24          # Rating change magnitude per match
```

### LLM Token Limits

```python
DEFAULT_MAX_TOKENS = 4000     # Standard responses
EXTENDED_MAX_TOKENS = 6000    # Longer responses
LONG_MAX_TOKENS = 8000        # Very long responses
THINKING_MAX_TOKENS = 16000   # Extended thinking models
```

### Temperature Settings

```python
LOW_TEMPERATURE = 0.3     # Ranking, tournament (consistency)
MEDIUM_TEMPERATURE = 0.5  # Meta-review, supervisor (balanced)
HIGH_TEMPERATURE = 0.7    # Generation, evolution, review (creativity)
```

Some models, especially thinking ones, require temperature=1 or ignore the parameter altogether to default to 1.

### Similarity Thresholds

```python
DUPLICATE_SIMILARITY_THRESHOLD = 0.95  # Remove near-identical hypotheses
PROXIMITY_SIMILARITY_THRESHOLD = 0.85  # Cluster similar hypotheses
```

### Modifying Constants

If you need to tune these parameters, edit `src/open_coscientist/constants.py`.

Modifying constants may affect result quality and should be done with careful evaluation.

## Performance Tuning

### For Speed

```python
generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",   # Fast, cheap model
    max_iterations=1,                       # Not many iterations
    initial_hypotheses_count=3,             # Smaller pool
    enable_cache=True,                      # Reuse responses
)
```

### For Quality

```python
generator = HypothesisGenerator(
    model_name="claude-sonnet-4-5-20250929",  # High-quality model
    max_iterations=4,                         # Multiple refinement cycles
    initial_hypotheses_count=8,               # Larger diverse pool
    evolution_max_count=6,                    # Evolve more hypotheses
)
```

### For Cost Optimization

```python
generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",   # Cost-effective model
    enable_cache=True,                      # Avoid redundant calls
    initial_hypotheses_count=5,             # Moderate pool size
)
```