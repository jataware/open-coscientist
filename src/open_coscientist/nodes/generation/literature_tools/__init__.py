"""
Tool-based literature generation - two-phase approach.

Phase 1 (draft.py): Read papers and draft hypotheses
Phase 2 (validate.py): Search literature and validate/refine novelty

Orchestrates both phases to generate hypotheses with dynamic literature access.
"""

import logging
from typing import List

from ....mcp_client import get_mcp_client
from ....models import Hypothesis
from ....state import WorkflowState
from ....tools.literature import literature_tools
from ....tools.provider import HybridToolProvider
from .draft import draft_hypotheses
from .validate import validate_hypotheses

logger = logging.getLogger(__name__)


async def generate_with_tools(
    state: WorkflowState,
    count: int
) -> List[Hypothesis]:
    """
    generate hypotheses with two-phase tool-based process (draft → validate)

    phase 1: draft hypotheses by reading papers and identifying gaps
    phase 2: validate novelty by searching and refining/pivoting

    args:
        state: current workflow state
        count: number of hypotheses to generate

    returns:
        list of validated hypotheses with generation_method="literature_tools"
    """
    logger.info(f"Generating {count} hypotheses with two-phase tool-based process")

    # get MCP client
    try:
        mcp_client = await get_mcp_client()
    except Exception as e:
        logger.warning(f"Failed to get MCP client: {e}")
        raise

    # note: draft and validate phases use separate tool whitelists
    # draft = read pre-curated papers, no search
    # validate = search for novelty checking

    # log article stats
    articles = state.get("articles", [])
    if articles:
        used_count = sum(1 for art in articles if art.used_in_analysis)
        logger.debug(
            f"state.articles contains {len(articles)} total articles, {used_count} with used_in_analysis=True"
        )
        if used_count > 0:
            articles_with_pdfs = sum(
                1 for art in articles if art.used_in_analysis and art.pdf_links
            )
            logger.info(
                f"Including {used_count} analyzed articles in prompt ({articles_with_pdfs} with PDFs, {used_count - articles_with_pdfs} abstract-only)"
            )
        else:
            logger.warning(
                "No articles with used_in_analysis=True found in state - agent will search fresh"
            )

    # Phase 1: Draft hypotheses (reads pre-curated papers)
    draft_hyps = await draft_hypotheses(state=state, count=count, mcp_client=mcp_client)

    logger.info(f"Phase 1 complete: drafted {len(draft_hyps)} hypotheses")

    # Phase 2: Validate and refine drafts (searches for novelty)
    hypotheses = await validate_hypotheses(
        state=state, draft_hypotheses=draft_hyps, mcp_client=mcp_client
    )

    logger.info(f"Phase 2 complete: validated {len(hypotheses)} hypotheses")

    # debug logging to verify generation_method
    for i, hyp in enumerate(hypotheses):
        logger.debug(
            f"tool-generated hypothesis {i+1}: generation_method={hyp.generation_method}, text={hyp.text[:80]}..."
        )

    return hypotheses


__all__ = ["draft_hypotheses", "validate_hypotheses", "generate_with_tools"]
