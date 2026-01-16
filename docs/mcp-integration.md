# MCP Integration & Literature Review

The MCP (Model Context Protocol) server integration is **recommended** for best results. While Open Coscientist will work without it, the quality of hypotheses is significantly enhanced when grounded in real published research.

## Initial Reference Literature Tools
### PubMed / Biomedical (Initial Scope)

For our initial release, we focus on the biomedical domain and provide integration with PubMed publications. This was made to:
- Minimize external dependencies (e.g. API keys, paid services)
- Keep the demo and CLI experience simple
- Align with early user interest in biomedical hypothesis generation
- Provide a well-structured, high-quality literature source for evaluation

The core engine is domain-agnostic by design. With appropriate prompt adaptations and MCP integrations, it can be extended to other research domains. PubMed serves as a concrete reference implementation, not a hard limitation.

## With MCP Server

Open Coscientist will:
- Automatically detect the MCP server at startup
- Search PubMed biomedical database for real published papers
- Retrieve fulltext XML/HTML from PubMed Central (PMC)
- Analyze literature with per-paper analysis and synthesis
- Use the Reflection node to validate hypotheses against actual research findings
- Generate hypotheses informed by current biomedical literature

**Limitations without MCP:**
- Relies solely on LLM's training data (limited awareness of recent discoveries)
- No validation against current scientific literature

## Setting Up MCP Server

### Quick Start with Docker

The easiest way to get started is with Docker:

```bash
# 1. copy and configure environment
cp mcp_server/.env.example mcp_server/.env
# edit mcp_server/.env: set ENTREZ_EMAIL and ENTREZ_API_KEY

# 2. start server with docker compose from project root (open-coscientist/)
docker compose up -d

# 3. verify server is running
curl http://localhost:8888
```

MCP endpoints will be available at `http://localhost:8888/mcp` (auto-detected by Open Coscientist).

### Alternative: Local Development Setup

For local development without Docker:

```bash
cd mcp_server

# create Python 3.12+ environment
python3.12 -m venv venv
source venv/bin/activate

# install dependencies
pip install -e .

# configure environment
cp .env.example .env
# edit .env: set ENTREZ_EMAIL, ENTREZ_API_KEY

# Run from root dir, to find the mcp_server package
cd ..

# run server (from root dir)
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888
```

**For complete setup instructions, Docker commands, and configuration options, see [mcp_server/README.md](../mcp_server/README.md).**

### Required Environment Variables (See mcp_server/.env.example)

MCP server requires:
- `ENTREZ_EMAIL`: Your email (required for PubMed API)
- `ENTREZ_API_KEY`: For higher rate limits (get at https://www.ncbi.nlm.nih.gov/account/)

## Generation Modes

Open Coscientist supports three generation modes with different levels of literature integration:

1. **No Literature Review** (Fastest) - Uses only LLM knowledge
2. **Literature-Informed Generation** - Pre-processes literature, then generates
3. **Tool-Calling Generation** - Generate node queries literature in real-time

**For detailed information on each mode, configuration examples, and when to use each, see [Generation Modes Documentation](generation-modes.md).**


## Extending MCP Tools

The MCP server can be extended with additional tools:

- Custom research databases
- Domain-specific literature sources
- Patent databases
- Preprint servers (arXiv, bioRxiv)
- Institutional repositories

When bringing or using tools from an external MCP server, with different tool names, signatures, or completely new integrations (eg search other sources),
you will need to modify the prompt template under `prompts/`, and potentially the related node code to ensure support for the tool.

Refer to the MCP specification for implementing custom tools: [Model Context Protocol](https://modelcontextprotocol.io)
