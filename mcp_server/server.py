"""
Open Coscientist literature review mcp server

Reference implementation using fastmcp for pubmed literature review tools.
Pubmed-only implementation for biomedical research.
"""

import os
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp import FastMCP

import fastmcp
fastmcp.settings.stateless_http = True

# import config early to load .env
from mcp_server import config

# configure logging based on .env
log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
# set root logger to INFO (default for all libraries)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logging.getLogger('mcp_server').setLevel(log_level)

from mcp_server.tools.lit_review.search_pubmed import check_pubmed_available, search_pubmed
from mcp_server.tools.lit_review.pubmed_search_with_fulltext import pubmed_search_with_fulltext

logger = logging.getLogger(__name__)

# log startup configuration
entrez_email_present = bool(os.environ.get("ENTREZ_EMAIL"))

logger.info(f"MCP server starting")
logger.debug(f"API keys present: ENTREZ_EMAIL={entrez_email_present}")

mcp = FastMCP("open-coscientist-lit-review")

# register literature review tools
mcp.tool(check_pubmed_available,       name="check_pubmed_available")
mcp.tool(search_pubmed,                name="search_pubmed")
mcp.tool(pubmed_search_with_fulltext,  name="pubmed_search_with_fulltext")

mcp_http_app = mcp.http_app()
app = FastAPI(lifespan=mcp_http_app.lifespan)

# add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """API status endpoint"""
    return JSONResponse({
        "status": "running",
        "service": "coscientist-lit-review",
        "version": "0.1.0",
        "mcp_tools": [
            "check_pubmed_available",
            "search_pubmed",
            "pubmed_search_with_fulltext"
        ],
        "api_keys_configured": {
            "ENTREZ_EMAIL": entrez_email_present
        }
    })

app.mount("/", mcp_http_app)

if __name__ == "__main__":
    port = int(os.environ.get("COSCIENTIST_MCP_PORT", 8888))
    uvicorn.run(app, host="0.0.0.0", port=port)
