# Development Test-Run Scripts

Meant for developers or contributors, although can be used by evaluators with coding skills.
Quick scripts for running individual nodes in isolation during _development_ or evaluation.

## Purpose

- Try out nodes independently without running full workflow (save time).
- Faster iteration when working on a specific node
- Minimal state setup; avoids mock data maintenance
- Still does LLM calls

## Setup

### install dev dependencies

Install optional dev dependencies (includes python-dotenv for .env support) on top-level package.

## Usage

Each script can be run directly with python:

```bash
# test supervisor node only
python dev/run_supervisor_standalone.py

# test literature review node (requires MCP server running)
python dev/run_lit_review_standalone.py

# test generate node
python dev/run_generate_standalone.py
```

## Environment Setup

### .env file

Create a `.env` file in this `dev/` directory:

```bash
cp .env.example .env
# edit .env with your api keys
```

Required keys:
- `GEMINI_API_KEY` - for LLM calls- gemini/gemini-2.5-flash hardcoded on these by default (can be customized)
- `MCP_SERVER_URL` - URL to your MCP server (default: http://localhost:8888/mcp)
Can't run the literature review node script if an MCP with the url/pdf reading tools is not available.
For now you'll have to see the source code to check what tools are expected or the LLM prompts used,
in the future we'll provide a reference implementation of it.

Optional keys:
- `COSCIENTIST_DEV_MODE=true` - use reduced paper counts for faster testing
- `COSCIENTIST_CACHE_ENABLED=false` - disable LLM caching for fresh responses


## Prerequisites

### For literature review tests

Start an MCP server before running `run_lit_review_standalone.py`.

The MCP server provides tools for literature search (Google Scholar, PubMed, etc.). You can use any MCP-compatible server, such as:
- The reference implementation in [beaker-coscientist-viewer](https://github.com/jataware/beaker-coscientist-viewer) (not yet publicly available)
- Your own custom MCP server implementing the required tools.

## Tips

- Use cheap models (gemini-2.5-flash) for quick tests
- These scripts use real LLM calls - check your API keys
- Logs are saved to logs/ directory with timestamps*

## State Helpers

`state_helpers.py` provides minimal state builders:
- `make_base_state()` - minimal required fields
- `make_supervisor_state()` - base + supervisor output
- `make_literature_state()` - base + literature review results

These create MINIMAL state to run nodes - just enough to not error.
They intentionally don't mock complex nested structures that would get out of sync.