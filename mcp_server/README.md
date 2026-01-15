# Open Coscientist MCP Server

MCP (Model Context Protocol) server providing PubMed literature search tools for Open Coscientist hypothesis generation.

## Features

Provides 2 core tools for biomedical literature search:

- **check_pubmed_available**: Test if PubMed service is accessible
- **pubmed_search_with_fulltext**: Search PubMed, download fulltext from PMC, and extract clean text for LLM analysis

## Quick Start (Docker)

**Prerequisites:**
- Docker and Docker Compose installed
- NCBI Entrez email (free, required for PubMed API), Entres API key recommended (free)

**Setup:**

```bash
# 1. copy environment template
cp .env.example .env

# 2. edit .env and add required keys:
    ENTREZ_EMAIL=your_email@example.com

# 3. start server from parent dir
cd ..        # to open-coscientist root folder
docker compose up -d

# 4. verify server is running
curl http://localhost:8888
```

MCP endpoints will be available at `http://localhost:8888/mcp`

## Alternative: Local Development Setup

**Prerequisites:**
- Python >=3.12
- Pip or UV package manager

```bash
# 1. create virtual environment (Python 3.12+)
python3.12 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# 2. install dependencies
pip install -e .

# 3. configure environment
cp .env.example .env
# edit .env and add ENTREZ_EMAIL and API keys

# Root dir, to find mcp_server package
cd ..

# 4. run server
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888

# or with auto-reload for development:
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888 --reload
```

## Configuration

### Required Environment Variables

```bash
# required for PubMed access
ENTREZ_EMAIL=your_email@example.com
# higher rate limits (optional)
ENTREZ_API_KEY=your_ncbi_api_key  # get at https://www.ncbi.nlm.nih.gov/account/
# then https://account.ncbi.nlm.nih.gov/settings/ -> API Key Management
```

### Optional Environment Variables

```bash
# server port (default: 8888)
COSCIENTIST_MCP_PORT=8888

# paper cache directory (default: ./paper_cache)
COSCIENTIST_LIT_REVIEW_DIR=./paper_cache
```

## Usage with Open Coscientist

Open Coscientist automatically connects to this MCP server if running.

Configure the MCP URL (optional, defaults to `http://localhost:8888/mcp`):

```bash
export MCP_SERVER_URL="http://localhost:8888/mcp"
```

The library will:
1. Check if MCP server is available
2. Use PubMed tools for literature review
3. Extract fulltext and analyze with LLM agents
4. Generate and validate hypotheses based on literature

## Architecture

```
mcp_server/
├── server.py                    # FastMCP server
├── config.py                    # Configuration
├── text_extraction.py           # PMC HTML to markdown
└── tools/
    └── lit_review/
        ├── search_pubmed.py              # check availability
        └── pubmed_search_with_fulltext.py  # search + fulltext
```

## Docker Details

**Environment:**
- Set required keys via `.env` file or docker compose environment

**Commands:**
```bash
# build image
docker compose build

# start in background
docker compose up -d

# view logs
docker compose logs -f

# stop server
docker compose down

# rebuild after code changes
docker compose up -d --build
```

## Support

For issues or questions:
- GitHub: https://github.com/jataware/open-coscientist
- Documentation: See main [README](../README.md)
