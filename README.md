# Open Coscientist

**AI-powered research hypothesis generation using LangGraph**

Open Coscientist is an open **adaptation based on Google Research's [AI Co-Scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/)** research paper. This project provides an implementation that generates, reviews, ranks, and evolves research hypotheses using the multi-agent architecture described. It orchestrates 8-10 specialized AI agents through a LangGraph workflow and aims to produce novel hypotheses grounded in scientific literature.

## Demo

<p align="center">
  <a href="https://youtu.be/LyOvigZ59yE?si=JiIJnXajgLhTb1yj">
    <img src="https://github.com/jataware/open-coscientist/blob/main/assets/Open_Coscientist_Demo.gif?raw=true" alt="Open Coscientist Demo">
  </a>
</p>

<p align="center">
  <em>
    In this demo we use Open Coscientist to generate hypotheses for novel approaches to early detection of Alzheimer's disease.
    Click to watch the full demo on YouTube.
  </em>
</p>

### Standalone operation

The engine works with any LLM and can run without external data sources.

For high-quality hypothesis generation, the system provides an MCP server integration to perform literature-aware reasoning over published research. See [MCP Integration](https://github.com/jataware/open-coscientist/blob/main/docs/mcp-integration.md) for setup and configuration details, and to run the basic reference MCP server.

## Quick Start

### Installation

```bash
pip install open-coscientist
```

Set your API key (any LiteLLM-supported provider):
```bash
export GEMINI_API_KEY="your-key-here"
# or: export ANTHROPIC_API_KEY="your-key-here"
# or: export OPENAI_API_KEY="your-key-here"
```

For development, see [CONTRIBUTING.md](https://github.com/jataware/open-coscientist/blob/main/CONTRIBUTING.md).

> **Note**: for the any literature review to run, you must provide an MCP server with literature review tools/capabilities. You can use the provided reference implementation [MCP Server](https://github.com/jataware/open-coscientist/tree/main/mcp_server). Otherwise, no published research will be used.

**Model Support**: Uses [LiteLLM](https://docs.litellm.ai/docs/providers) for 100+ LLM providers (OpenAI, Anthropic, Google, Azure, AWS Bedrock, Cohere, etc.). May need to tweak some constants.py token usage and other params, such as initial hypotheses count, in order to work with less powerful models.

### Basic Usage

```python
import asyncio
from open_coscientist import HypothesisGenerator

async def main():
    generator = HypothesisGenerator(
        model_name="gemini/gemini-2.5-flash", # default model if not provided
        max_iterations=1,
        initial_hypotheses_count=5,
        evolution_max_count=3
    )

async for node_name, state in generator.generate_hypotheses(
    research_goal="Your research question",
    stream=True
):
    print(f"Completed: {node_name}")
    if node_name == "generate":
        print(f"Generated {len(state['hypotheses'])} hypotheses")

if __name__ == "__main__":
    asyncio.run(main())
```

See [`examples/run.py`](https://github.com/jataware/open-coscientist/blob/main/examples/run.py) for a full example cli script with a built-in Console Reporter. **Remember**, you must run the literature review MCP server for any literature review to be included in the hypothesis generation.

## Features

- **Multi-agent workflow**: Supervisor, Generator, Reviewer, Ranker, Tournament Judge, Meta-Reviewer, Evolution, Proximity Deduplication
- **Literature review integration**: Optional MCP server provides access to real published research
- **Real-time streaming**: Stream results as they're generated
- **Intelligent caching**: Faster development iteration with LLM response caching
- **Elo-based tournament**: Pairwise hypothesis comparison with Elo ratings
- **Iterative refinement**: Evolves top hypotheses while preserving diversity

The workflow automatically detects MCP availability and adjusts accordingly.
Functional reference MCP server included in `mcp_server/` directory.

## Documentation

- **[Architecture](https://github.com/jataware/open-coscientist/blob/main/docs/architecture.md)** - Workflow diagram, node descriptions, state management
- **[MCP Integration](https://github.com/jataware/open-coscientist/blob/main/docs/mcp-integration.md)** - Literature review setup and configuration
- **[Generation Modes](https://github.com/jataware/open-coscientist/blob/main/docs/generation-modes.md)** - Three generate node modes explained, and parameters to enable them
- **[Configuration](https://github.com/jataware/open-coscientist/blob/main/docs/configuration.md)** - All parameters, caching, performance tuning
- **[Logging](https://github.com/jataware/open-coscientist/blob/main/docs/logging.md)** - File logging, rotating logs, log levels
- **[Development](https://github.com/jataware/open-coscientist/blob/main/docs/development.md)** - Contributing, node structure, testing

### Node Descriptions

| Node | Purpose | Key Operations |
|------|---------|----------------|
| **Supervisor** | Research planning | Analyzes research goal, identifies key areas, creates workflow strategy |
| **Literature Review** *(Recommended)* | Academic literature search | Queries databases (PubMed, Google Scholar), retrieves and analyzes real published papers (requires MCP server; without it, uses only LLM's latent knowledge) |
| **Generate** | Hypothesis creation | Generates N initial hypotheses using LLM with high temperature for diversity |
| **Reflection** *(Recommended)* | Literature comparison | Analyzes hypotheses against literature review findings, identifies novel contributions and validates against real research (requires literature review) |
| **Review** | Adaptive evaluation | Reviews hypotheses across 6 criteria using adaptive strategy (comparative batch for ≤5, parallel for >5) |
| **Rank** | Holistic ranking | LLM ranks all hypotheses considering composite scores and review feedback |
| **Tournament** | Pairwise comparison | Runs Elo tournament with random pairwise matchups, updates ratings |
| **Meta-Review** | Insight synthesis | Analyzes all reviews to identify common strengths, weaknesses, and strategic directions |
| **Evolve** | Hypothesis refinement | Refines top-k hypotheses with context awareness to preserve diversity |
| **Proximity** | Deduplication | Clusters similar hypotheses and removes high-similarity duplicates |

## Literature Review
Our MCP server reference implementation is meant to provide a template for how to integrate literature review with Open Coscientist. It is by no means extensive and currently only supports PubMed. See [MCP Integration](https://github.com/jataware/open-coscientist/blob/main/docs/mcp-integration.md) for more on how to extend this reference implementation to meet your needs.

## Attribution

Open Coscientist is a source-available implementation inspired by Google Research's AI Co-Scientist. While Google's original system is closed-source, this project adapts their multi-agent hypothesis generation architecture from their published research paper.

**Reference:**
- **Blog**: [Accelerating scientific breakthroughs with an AI Co-Scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/)
- **Paper**: [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)

This version provides a LangGraph-based implementation. It includes some optimizations for parallel execution, streaming support, and caching.

## Citation

If you use this work, please cite both this implementation and the original Google Research paper:

```bibtex
@article{coscientist2025,
  title={Towards an AI co-scientist},
  author={Google Research Team},
  journal={arXiv preprint arXiv:2502.18864},
  year={2025},
  url={https://arxiv.org/abs/2502.18864}
}
```
