# Generation Modes and Literature Review Configuration

This document explains how hypothesis generation works with different literature review configurations in Open Coscientist.

## Generation Modes Explained

Open Coscientist supports three main generation modes depending on your configuration:

### Mode 1: No Literature Review (Fastest)

```python
opts = {"enable_literature_review_node": False}
```

**Workflow:**
```
Supervisor → Generate → Review → Ranking → (Iterations...)
```

**Generation strategies used:**
- Standard generation (relies on LLM's latent knowledge)
- Debate generation (multi-agent perspective generation)

**Characteristics:**
- Fastest execution time
- No external literature queries
- Good for exploratory brainstorming
- No MCP server needed

**Use cases:**
- Quick prototyping
- Testing workflow without infrastructure
- Brainstorming sessions
- Initial engine evaluation, understanding

---

### Mode 2: Literature-Informed Generation (Recommended)

```python
opts = {"enable_literature_review_node": True}  # Default if MCP available
```

**Workflow:**
```
Supervisor → Literature Review → Generate → Reflection → Review → Ranking → (Iterations...)
```

**Generation strategies used:**
- Literature generation (uses pre-processed literature review summaries)
- Debate generation (multi-agent perspective generation)

**Characteristics:**
- Balanced speed and literature integration
- Literature Review node runs once at the start
- Generate node receives processed literature summaries
- Reflection node compares hypotheses to literature
- Good balance of speed and quality

**Use cases:**
- Most research tasks
- When you want literature-grounded hypotheses
- Standard production usage
- Best balance of speed and literature integration

---

### Mode 3: Tool-Calling during Generation (Better results, slower)

```python
opts = {
    "enable_literature_review_node": True,  # Required
    "enable_tool_calling_generation": True
}
```

**Workflow:**
```
Supervisor → Literature Review → Generate (with tools) → Reflection → Review → Ranking → (Iterations...)
```

**Generation strategies used:**
- Tool-calling generation (Generate node queries literature tools directly for each hypothesis)
- Debate generation (multi-agent perspective generation)

**Characteristics:**
- Most literature-aware hypotheses
- Generate node makes real-time literature queries per hypothesis
- Two-phase generation process
- Slower but highest literature integration
- Falls back to Mode 2 if tool calls fail

**Use cases:**
- More/max literature grounding needed
- Each hypothesis requires specific literature support
- Research requiring deep citation integration
- Advanced production use cases

**Requirements:**
- MCP server must be running
- `enable_literature_review_node=True` must be set
- Will fall back to Mode 2 (standard literature generation) if MCP unavailable

**Important:** If you try to enable this without the literature review node, you'll get a validation error.

### `dev_test_lit_tools_isolation` (boolean)

Development/testing mode for isolating tool-calling generation behavior.

- **Default**: `False`
- **Purpose**: Forces all hypotheses through tool-calling generation (no debate), forces literature review _node_ caching
- **Use case**: Testing and debugging Generate node (with lit review mcp tools) in isolation

**Only use for development/testing.**

---

## How Literature Review Works

### Literature Review Node

When `enable_literature_review_node=True`:

1. **Query Generation**: Supervisor creates research plan, Literature Review node generates targeted search queries
2. **Paper Search**: Queries PubMed via MCP tools
4. **Summary Creation**: Creates formatted literature summary for downstream nodes

The summary of the review is stored in `state["articles_with_reasoning"]` and used by:
- Generate node (Mode 2: pre-processed summaries, Mode 3: direct tool access)
- Reflection node (compares hypotheses to literature findings)

The articles used are stored in `state[articles]`, which will contain all articles that resulted from the search,
 as well as an annotation (property) `used_in_analysis` if the article was used to create the `articles_with_reasoning` review.

### Reflection Node

Only runs when `enable_literature_review_node=True`. Compares each generated hypothesis against literature review findings and provides feedback on:
- How well the hypothesis is supported by existing research
- Novel aspects not covered in literature
- Potential gaps or conflicts with existing studies

## Error Handling

### MCP Server Unavailable

**If you request literature review but MCP server is unavailable:**

```python
opts = {"enable_literature_review_node": True}
# MCP server not running
```

**Behavior:**
- Logs warning: "literature review node requested but mcp server unavailable - disabling"
- Automatically disables literature review node
- Falls back to Mode 1 (no literature review), also known as "standard".
- Generation continues without error

---

## MCP Server Setup


See [MCP Integration](mcp-integration.md) documentation.


## Examples

### Example 1: Basic Usage (No Literature)

```python
from open_coscientist import HypothesisGenerator

generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",
    max_iterations=1,
    initial_hypotheses_count=5
)

result = await generator.generate_hypotheses(
    research_goal="Develop novel cancer treatments",
    opts={"enable_literature_review_node": False}
)
```

### Example 2: Literature-Informed

```python
from open_coscientist import HypothesisGenerator

generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",
    max_iterations=1,
    initial_hypotheses_count=5
)

# Auto-enables if MCP available, or explicitly enable
result = await generator.generate_hypotheses(
    research_goal="Develop novel cancer treatments",
    opts={"enable_literature_review_node": True}
)
```

### Example 3: Generate Initial Hypotheses with Tool-Calling Mode

```python
from open_coscientist import HypothesisGenerator

generator = HypothesisGenerator(
    model_name="gemini/gemini-2.5-flash",
    max_iterations=1,
    initial_hypotheses_count=5
)

result = await generator.generate_hypotheses(
    research_goal="Develop novel cancer treatments",
    opts={
        "enable_literature_review_node": True,  # Required
        "enable_tool_calling_generation": True
    }
)
```