# Development Guide

Guide for contributors and developers working on Open Coscientist internals.

## Project Structure

```
open-coscientist/
├── src/
│   └── open_coscientist/
│       ├── __init__.py
│       ├── generator.py        # HypothesisGenerator class, LangGraph setup
│       ├── state.py            # WorkflowState TypedDict
│       ├── schemas.py          # JSON schemas for LLM responses
│       ├── models.py           # Hypothesis, Article dataclasses (among others)
│       ├── llm.py              # LLM calling utilities
│       ├── cache.py            # LLM response caching
│       ├── mcp_client.py       # MCP server integration
│       ├── constants.py        # Configuration constants
│       ├── nodes/              # Individual node implementations
│       │   ├── __init__.py
│       │   ├── supervisor.py
│       │   ├── literature_review.py
│       │   ├── generate.py
│       │   ├── review.py
│       │   ├── rank.py
│       │   ├── meta_review.py
│       │   ├── evolve.py
│       │   ├── proximity.py
│       │   └── reflection.py
│       └── prompts/            # Markdown prompt templates
│           ├── supervisor.md
│           ├── generate.md
│           ├── review.md
│           └── ...
├── examples/
│   ├── basic_usage.py
│   └── with_literature_review.py
├── mcp_server/                 # Reference MCP server implementation
├── docs/                       # Documentation
```

## Node Structure

Each node is an async function that follows a consistent pattern:

```python
from typing import Dict, Any
from ..state import WorkflowState
from ..llm import call_llm_json

async def node_name(state: WorkflowState) -> Dict[str, Any]:
    """
    Brief description of what this node does.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with state updates to merge
    """
    # 1. Extract relevant state
    hypotheses = state["hypotheses"]
    research_goal = state["research_goal"]

    # 2. Perform operation (often with LLM call)
    response = await call_llm_json(
        prompt="Your prompt here",
        model_name=state["model_name"],
        temperature=0.7,
        max_tokens=4000,
        json_schema=YourSchema,
    )

    # 3. Update metrics
    metrics = create_metrics_update(...)
    result["metrics"] = metrics

    # 4. Process results and update hypotheses
    for hyp in hypotheses:
        # Update hypothesis based on node operation
        pass

    # 5. Return state updates (only changed fields)
    return {
        "hypotheses": hypotheses,
        "metrics": metrics,
        "messages": [f"{node_name} completed"],
    }
```

## Adding a New Node

### 1. Create Node File

Create `src/open_coscientist/nodes/my_node.py`:

```python
from typing import Dict, Any
from ..state import WorkflowState
from ..llm import call_llm_json

async def my_node(state: WorkflowState) -> Dict[str, Any]:
    """Your node implementation."""
    # Implementation here
    return {"hypotheses": state["hypotheses"]}
```

### 2. Create Prompt Template

Create `src/open_coscientist/prompts/my_node.md`:

```markdown
# My Node Prompt

Your prompt instructions here.

## Research Goal
{research_goal}

## Hypotheses
{hypotheses}
```

### 3. Add to Workflow Graph

Update `src/open_coscientist/generator.py`:

```python
from .nodes.my_node import my_node

# In HypothesisGenerator.__init__:
workflow.add_node("my_node", my_node)
workflow.add_edge("previous_node", "my_node")
workflow.add_edge("my_node", "next_node")
```

### 4. Update State Type (if needed)

If your node adds new state fields, update `src/open_coscientist/state.py`:

```python
class WorkflowState(TypedDict, total=False):
    # Existing fields...
    my_new_field: str  # Add your field
```

## Working with State

### WorkflowState Fields

| Field | Type | Description |
|-------|------|-------------|
| `research_goal` | `str` | Original research question |
| `research_plan` | `str` | Strategy from supervisor |
| `hypotheses` | `List[Dict]` | Current hypothesis pool |
| `articles_with_reasoning` | `str` | Literature summary (if MCP available) |
| `articles` | `List[Dict]` | Retrieved papers (literature review) |
| `metrics` | `Metrics` | Performance tracking |

There are many other fields. Inspect state as each node completed or view state.py for other captured state.

### Hypothesis Structure

Each hypothesis is a dictionary. See models.py for its shape and properties.

## LLM Calling

### Standard JSON Response

```python
from open_coscientist.llm import call_llm_json

response = await call_llm_json(
    prompt="Your prompt",
    model_name="gemini/gemini-2.5-flash",
    temperature=0.7,
    max_tokens=4000,
    json_schema=MySchema, # uses schema where possible to avoid brittleness
)
```

### With Tool Calling (MCP)

```python
from open_coscientist.mcp_client import get_mcp_tools

tools = await get_mcp_tools()
response = await call_llm_with_tools(
    prompt="Your prompt",
    tools=tools,
    model_name="gemini/gemini-2.5-flash",
)
```

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("open_coscientist")
```

### Inspect State Between Nodes

```python
async for node_name, state in generator.generate_hypotheses(research_goal, stream=True):
    print(f"\n{node_name} completed")
    print(f"Hypotheses: {len(state['hypotheses'])}")
    print(f"Metrics: {state['metrics']}")
```

### Cache Debugging

```python
from open_coscientist import get_cache_stats

# Check what's cached
stats = get_cache_stats()
print(f"Cached: {stats['cache_files']} responses")

# Clear cache to force fresh LLM calls
from open_coscientist import clear_cache
clear_cache()
```

## Performance Optimization

### Parallel Execution

Use `asyncio.gather()` for parallel operations:

```python
import asyncio

# Run reviews in parallel
review_tasks = [
    review_single_hypothesis(hyp, state)
    for hyp in hypotheses
]
results = await asyncio.gather(*review_tasks)
```

### Token Optimization
- Use shorter prompts when possible
- Batch similar operations (comparative review)
- Use appropriate max_tokens limits

## Contributing

### Prompt Engineering

- Store prompts in `prompts/` as markdown files
- Use clear section headers
- Include examples in prompts
- Test prompts with multiple models

## Advanced Topics

### Extending MCP Tools

Add new tools to the MCP server for domain-specific needs:

- Custom databases
- Domain-specific validators
- Simulation runners
- Data analysis tools

See [MCP Integration](mcp-integration.md) for details.
