"""
Phase 2: Validate novelty and refine/pivot draft hypotheses.

This phase uses a two-stage approach:
1. Per-hypothesis per-paper novelty analysis (parallel)
2. Synthesis agent decides approve/refine/pivot based on analyses
"""

import asyncio
import json
import logging
from typing import Any, Dict, List

from ....constants import (
    EXTENDED_MAX_TOKENS,
    GENERATE_LIT_TOOL_MAX_PAPERS,
    HIGH_TEMPERATURE,
    INITIAL_ELO_RATING,
)
from ....llm import call_llm_json
from ....models import Hypothesis
from ....prompts import (
    get_hypothesis_novelty_analysis_prompt,
    get_hypothesis_validation_synthesis_prompt
)
from ....schemas import (
    HYPOTHESIS_NOVELTY_ANALYSIS_SCHEMA,
    HYPOTHESIS_VALIDATION_SYNTHESIS_SCHEMA
)
from ....state import WorkflowState

logger = logging.getLogger(__name__)


async def validate_hypotheses(
    state: WorkflowState,
    draft_hypotheses: List[Dict[str, str]],
    mcp_client: Any
) -> List[Hypothesis]:
    """
    Phase 2: validate novelty and refine/pivot drafts

    Two-stage approach:
    1. per-hypothesis per-paper novelty analysis (parallel)
    2. synthesis agent decides approve/refine/pivot

    args:
        state: current workflow state
        draft_hypotheses: list of draft dicts from Phase 1
        mcp_client: MCP client for PubMed search access

    returns:
        list of validated Hypothesis objects with novelty_validation
    """
    logger.info(f"Phase 2: Validating {len(draft_hypotheses)} draft hypotheses")

    # get state variables
    run_id = state.get("run_id")
    research_goal = state["research_goal"]

    # get shared slug from draft phase (warm corpus reuse)
    shared_slug = state.get("generation_corpus_slug")
    if not shared_slug:
        # fallback if draft phase didn't set it
        import hashlib

        shared_slug = "research_" + hashlib.md5(research_goal.encode()).hexdigest()[:8]
        logger.warning(f"Draft phase didn't set corpus slug, using fallback: {shared_slug}")
    else:
        logger.info(f"Reusing shared corpus from draft phase: {shared_slug}")

    # stage 1: per-hypothesis novelty analysis
    hypotheses_with_analyses = []

    for idx, draft in enumerate(draft_hypotheses, 1):
        hypothesis_text = draft.get("text", "")
        logger.info(
            f"Analyzing hypothesis {idx}/{len(draft_hypotheses)}: {hypothesis_text[:80]}..."
        )

        # search for papers related to this hypothesis
        try:
            search_result = await mcp_client.call_tool(
                "pubmed_search_with_fulltext",
                query=hypothesis_text[:200],  # use hypothesis text as query
                max_papers=GENERATE_LIT_TOOL_MAX_PAPERS,
                slug=shared_slug,
                run_id=run_id,
            )

            # parse result (mcp returns JSON string)
            if isinstance(search_result, str):
                papers = json.loads(search_result)
            else:
                papers = search_result

            logger.info(f"Found {len(papers)} papers for hypothesis {idx}")

        except Exception as e:
            logger.error(f"Failed to search papers for hypothesis {idx}: {e}")
            papers = {}

        # stage 1a: analyze each paper in parallel for this hypothesis
        novelty_analysis_tasks = []

        async def analyze_paper_novelty(paper_id: str, metadata: dict) -> dict:
            """Analyze single paper for novelty assessment"""
            fulltext = metadata.get("fulltext", "")

            # truncate if too long
            max_chars = 200_000
            if len(fulltext) > max_chars:
                fulltext = fulltext[:max_chars] + "\n\n[... truncated for length ...]"

            # extract paper info
            title = metadata.get("title", "Unknown")
            authors = metadata.get("authors", [])
            year = metadata.get("year")

            # get analysis prompt
            prompt = get_hypothesis_novelty_analysis_prompt(
                hypothesis_text=hypothesis_text,
                title=title,
                authors=authors,
                year=year,
                fulltext=fulltext,
            )

            # call LLM for structured analysis
            try:
                analysis = await call_llm_json(
                    prompt=prompt,
                    model_name=state["model_name"],
                    json_schema=HYPOTHESIS_NOVELTY_ANALYSIS_SCHEMA,
                    max_tokens=EXTENDED_MAX_TOKENS,
                    temperature=HIGH_TEMPERATURE,
                )

                return {
                    "paper_metadata": {"paper_id": paper_id, "title": title, "year": year},
                    "analysis": analysis,
                }
            except Exception as e:
                logger.error(f"Failed to analyze paper {paper_id} for hypothesis {idx}: {e}")
                return None

        # analyze all papers in parallel
        for paper_id, metadata in papers.items():
            task = analyze_paper_novelty(paper_id, metadata)
            novelty_analysis_tasks.append(task)

        if novelty_analysis_tasks:
            logger.info(
                f"Running {len(novelty_analysis_tasks)} novelty analyses in parallel for hypothesis {idx}"
            )
            novelty_analyses_results = await asyncio.gather(*novelty_analysis_tasks)

            # filter out failed analyses
            novelty_analyses = [a for a in novelty_analyses_results if a is not None]
            logger.info(f"Completed {len(novelty_analyses)} novelty analyses for hypothesis {idx}")
        else:
            novelty_analyses = []
            logger.warning(f"No papers with fulltext found for hypothesis {idx}")

        # collect hypothesis with its analyses
        hypotheses_with_analyses.append({"draft": draft, "novelty_analyses": novelty_analyses})

    # stage 2: synthesis - decide approve/refine/pivot for all hypotheses
    # process in batches to avoid token limit issues with many hypotheses
    BATCH_SIZE = 6  # process 6 hypotheses per synthesis call
    total_hypotheses = len(hypotheses_with_analyses)

    logger.info(f"Running validation synthesis for {total_hypotheses} hypotheses in batches of {BATCH_SIZE}")

    # batch hypotheses
    batches = []
    for i in range(0, total_hypotheses, BATCH_SIZE):
        batch = hypotheses_with_analyses[i:i + BATCH_SIZE]
        batches.append(batch)

    logger.info(f"Split into {len(batches)} batches")

    # process each batch
    async def process_synthesis_batch(batch: List[Dict[str, Any]], batch_num: int) -> List[Dict[str, Any]]:
        """Process a single batch of hypotheses through synthesis"""
        batch_size = len(batch)
        logger.info(f"Processing synthesis batch {batch_num}/{len(batches)} ({batch_size} hypotheses)")

        synthesis_prompt = get_hypothesis_validation_synthesis_prompt(
            research_goal=research_goal, hypotheses_with_analyses=batch
        )

        # scale token budget based on batch size
        # each hypothesis needs ~2500-3500 tokens for complete justification + validation
        synthesis_max_tokens = min(EXTENDED_MAX_TOKENS + (batch_size * 2500), 20000)
        logger.debug(
            f"Batch {batch_num} token budget: {synthesis_max_tokens} for {batch_size} hypotheses"
        )

        # call synthesis agent with structured JSON schema
        try:
            response_data = await call_llm_json(
                prompt=synthesis_prompt,
                model_name=state["model_name"],
                json_schema=HYPOTHESIS_VALIDATION_SYNTHESIS_SCHEMA,
                max_tokens=synthesis_max_tokens,
                temperature=HIGH_TEMPERATURE,
            )
            logger.debug(
                f"Batch {batch_num} synthesis returned {len(response_data.get('hypotheses', []))} hypotheses"
            )
            return response_data.get("hypotheses", [])
        except Exception as e:
            logger.error(f"Validation synthesis failed for batch {batch_num}: {e}")
            raise

    # process all batches in parallel
    batch_tasks = [
        process_synthesis_batch(batch, i + 1)
        for i, batch in enumerate(batches)
    ]

    batch_results = await asyncio.gather(*batch_tasks)

    # combine all validated hypotheses from batches
    all_validated_hypotheses = []
    for batch_hypotheses in batch_results:
        all_validated_hypotheses.extend(batch_hypotheses)

    logger.info(f"Combined {len(all_validated_hypotheses)} validated hypotheses from {len(batches)} batches")

    # create Hypothesis objects from synthesis
    hypotheses = []
    for hyp_data in all_validated_hypotheses:
        hypothesis = Hypothesis(
            text=hyp_data.get("text", ""),
            justification=hyp_data.get("justification"),
            literature_review_used=hyp_data.get("literature_review_used"),
            novelty_validation=hyp_data.get("novelty_validation"),
            score=0.0,
            elo_rating=INITIAL_ELO_RATING,
            generation_method="literature_tools",
        )
        hypotheses.append(hypothesis)

    logger.info(f"Generated {len(hypotheses)} validated hypotheses")
    return hypotheses
