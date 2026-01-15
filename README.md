# Open Coscientist

**AI-powered research hypothesis generation using LangGraph**

Open Coscientist is an open-source **adaptation based on Google Research's [AI Co-Scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/)** research paper. This project provides an open implementation that generates, reviews, ranks, and evolves research hypotheses using the multi-agent architecture described. It orchestrates 8-10 specialized AI agents through a LangGraph workflow and aims to produce novel hypotheses grounded in scientific literature.

## Demo

[![Demo](https://github.com/jataware/coscientist-lg/blob/open-source-rename-legal/assets/Open_Coscientist_Demo.gif?raw=true)](https://youtu.be/LyOvigZ59yE?si=JiIJnXajgLhTb1yj)

_Click to watch full demo on YouTube_

### Standalone operation

The engine works with any LLM and can run without external data sources.

For high-quality hypothesis generation, the system provides an MCP server integration to perform literature-aware reasoning over published research. See [MCP Integration](docs/mcp-integration.md) for setup and configuration details, and to run the basic reference MCP server.

## Quick Start

### Installation

```bash
git clone https://github.com/jataware/open-coscientist.git
cd open-coscientist
pip install .

# Set your API key (any LiteLLM-supported provider)
export GEMINI_API_KEY="your-key-here"
# or: export ANTHROPIC_API_KEY="your-key-here"
# or: export OPENAI_API_KEY="your-key-here"
```

For the default literature review step to run, setup the included [Mcp Server](./mcp_server).
Else no published research will be used.

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

See [`examples/run.py`](examples/run.py) for a full example cli script with a built-in Console Reporter.

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

- **[Architecture](docs/architecture.md)** - Workflow diagram, node descriptions, state management
- **[MCP Integration](docs/mcp-integration.md)** - Literature review setup and configuration
- **[Generation Modes](docs/generation-modes.md)** - Three generate node modes explained, and parameters to enable them
- **[Configuration](docs/configuration.md)** - All parameters, caching, performance tuning
- **[Logging](docs/logging.md)** - File logging, rotating logs, log levels
- **[Development](docs/development.md)** - Contributing, node structure, testing

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

## Attribution

Open Coscientist is an open-source implementation inspired by Google Research's AI Co-Scientist. While Google's original system is closed-source, this project reimplements their multi-agent hypothesis generation architecture based on their published research paper.

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