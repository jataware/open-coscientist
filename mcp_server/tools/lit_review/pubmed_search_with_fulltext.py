"""
Enhanced pubmed search that downloads fulltexts from pmc.

Wraps PubmedSource.pubmed_search() from literature_review.py to provide
Search + fulltext download + text extraction as a single mcp tool.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict
from Bio import Entrez

from mcp_server.literature_review import PubmedSource, LiteratureReviewAgent
from mcp_server.text_extraction import extract_text_from_pmc_html

logger = logging.getLogger(__name__)


async def pubmed_search_with_fulltext(
    query: str,
    slug: str,
    max_papers: int = 10,
    recency_years: int = 0,
    run_id: str = None
) -> Dict[str, Any]:
    """
    Search pubmed and download fulltexts (html from pmc).

    Initializes entrez credentials from environment and performs search
    with fulltext download. html-only implementation.

    Uses shared pool architecture - papers stored in slug/shared/ and symlinked
    to slug/runs/{run_id}/ for per-run isolation.

    args:
        query: pubmed boolean query (AND/OR/NOT operators)
        slug: snake_case identifier for organizing results (research goal hash)
        max_papers: maximum papers to retrieve
        recency_years: filter to papers from last N years (0 = no filter)
        run_id: unique run identifier for this execution (enables per-run tracking)

    returns:
        Dict mapping paper_id to metadata (title, abstract, authors, doi, pmc_full_text_id, etc.)
    """
    # initialize entrez credentials
    if (entrez_email := os.environ.get("ENTREZ_EMAIL", None)):
        Entrez.email = entrez_email
    else:
        logger.warning("ENTREZ_EMAIL not set - pubmed may rate limit or fail")

    if (entrez_key := os.environ.get("ENTREZ_API_KEY", None)):
        Entrez.api_key = entrez_key

    # initialize literature review agent
    lit_review_dir = Path(os.getenv("COSCIENTIST_LIT_REVIEW_DIR", "./cache/literature_review"))
    lit_review_dir.mkdir(parents=True, exist_ok=True)

    agent = LiteratureReviewAgent(lit_review_dir)
    pubmed_source = PubmedSource()
    agent.add_source("pubmed", pubmed_source)

    # fetch papers with fulltexts (pass run_id for per-run tracking)
    logger.info(f"Searching pubmed with query: {query}, slug: {slug}, run_id: {run_id}, max_papers: {max_papers}, recency_years: {recency_years}")
    results = await agent.fetch_for_query("pubmed", query, slug, max_papers, recency_years, run_id)

    logger.info(f"Pubmed search complete - found {len(results)} papers")

    # extract fulltext from HTML and add to metadata
    base_dir = lit_review_dir / "pubmed" / slug
    run_dir = base_dir / "runs" / run_id if run_id else base_dir

    papers_with_fulltext = 0
    for paper_id, metadata in results.items():
        pmc_id = metadata.get('pmc_full_text_id')
        if pmc_id:
            try:
                # read HTML from cache
                html_file = run_dir / f"{pmc_id}.fulltext.html"
                if html_file.exists():
                    with open(html_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()

                    # extract clean text/markdown
                    text = extract_text_from_pmc_html(html_content)
                    metadata['fulltext'] = text
                    papers_with_fulltext += 1
                    logger.debug(f"extracted {len(text)} chars from {pmc_id}")
                else:
                    logger.warning(f"Fulltext file not found for {pmc_id} at {html_file}")
            except Exception as e:
                logger.error(f"Failed to extract text from {pmc_id}: {e}")

    logger.info(f"Extracted fulltext for {papers_with_fulltext}/{len(results)} papers")

    return results
