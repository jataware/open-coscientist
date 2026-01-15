"""
Literature review node.

- Check entrez credentials, generate pubmed queries with llm
- Collect papers with pubmed_search_with_fulltext
- Analyze each paper for gaps/limitations/future work
- Synthesize across papers to create articles_with_reasoning
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict

from ..constants import (
    DEFAULT_MAX_TOKENS,
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    LITERATURE_REVIEW_PAPERS_COUNT,
    LITERATURE_REVIEW_PAPERS_COUNT_DEV,
    LITERATURE_REVIEW_RECENCY_YEARS,
    LITERATURE_REVIEW_FAILED,
)
from ..cache import get_node_cache
from ..llm import call_llm, call_llm_json
from ..mcp_client import get_mcp_client, check_pubmed_available_via_mcp
from ..models import Article
from ..prompts import (
    get_literature_review_query_generation_pubmed_prompt,
    get_literature_review_paper_analysis_prompt,
    get_literature_review_synthesis_prompt,
)
from ..schemas import LITERATURE_QUERY_SCHEMA, LITERATURE_PAPER_ANALYSIS_SCHEMA
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def literature_review_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Conduct literature review using pubmed with direct llm analysis.

    phase 1: generate pubmed queries with llm
    phase 2: collect papers with fulltexts from pmc
    phase 3: analyze each paper for gaps, limitations, future work (parallel)
    phase 4: synthesize across papers to create articles_with_reasoning
    phase 5: return results with article objects

    args:
        state: current workflow state

    returns:
        dictionary with updated state fields
    """
    logger.info("Starting literature review node (PubMed-only)")

    # check node cache first (before any mcp/llm calls)
    node_cache = get_node_cache()
    cache_params = {"research_goal": state["research_goal"]}

    # force cache in dev isolation mode (for testing lit tools generation)
    force_cache = state.get("dev_test_lit_tools_isolation", False)
    if force_cache:
        logger.info("Dev isolation mode: forcing literature review cache")

    cached_output = node_cache.get("literature_review", force=force_cache, **cache_params)
    if cached_output is not None:
        logger.info("Literature review cache hit")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_complete",
                {
                    "message": "Literature review completed (cached)",
                    "progress": 0.2,
                    "cached": True,
                },
            )

        return cached_output

    # test if pubmed is available via mcp
    pubmed_available = await check_pubmed_available_via_mcp()
    if not pubmed_available:
        logger.error("PubMed MCP service unavailable - literature review disabled")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_error",
                {"message": "Literature review failed (pubmed unavailable)", "progress": 0.2},
            )

        return {
            "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
            "literature_review_queries": [],
            "articles": [],
            "messages": [
                {
                    "role": "assistant",
                    "content": "literature review failed - pubmed service unavailable",
                    "metadata": {"phase": "literature_review", "error": True},
                }
            ],
        }

    # detect dev mode from environment (for faster testing with reduced paper counts)
    is_dev_mode = os.getenv("COSCIENTIST_DEV_MODE", "false").lower() in ("true", "1", "yes")
    papers_to_read_count = (
        LITERATURE_REVIEW_PAPERS_COUNT_DEV if is_dev_mode else LITERATURE_REVIEW_PAPERS_COUNT
    )

    logger.info(
        f"Literature review config: dev_mode={is_dev_mode}, papers_count={papers_to_read_count}"
    )

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "literature_review_start",
            {"message": "Conducting literature review with pubmed...", "progress": 0.1},
        )

    # initialize mcp client
    mcp_client = await get_mcp_client()

    # get optional fields
    preferences = state.get("preferences", "")
    attributes = state.get("attributes", [])
    user_hypotheses = state.get("starting_hypotheses", [])
    user_literature = state.get("literature", [])

    # ===========================================
    # phase 1: generate pubmed queries with llm
    # ===========================================
    logger.info("Phase 1: generating PubMed queries")

    query_generation_prompt = get_literature_review_query_generation_pubmed_prompt(
        research_goal=state["research_goal"],
        preferences=preferences,
        attributes=attributes,
        user_literature=user_literature,
        user_hypotheses=user_hypotheses,
    )

    # generate queries with structured json output
    try:
        queries_json = await call_llm_json(
            prompt=query_generation_prompt,
            model_name=state["model_name"],
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=HIGH_TEMPERATURE,
            json_schema=LITERATURE_QUERY_SCHEMA,
        )

        # extract queries from structured response
        queries = queries_json.get("queries", [])

        if not queries:
            logger.warning("No queries generated, using research goal")
            queries = [state["research_goal"]]

        # limit to 3 queries max
        queries = queries[:3]

        logger.info(f"Generated {len(queries)} PubMed queries")
        for i, q in enumerate(queries, 1):
            logger.debug(f"query {i}: {q}")

    except Exception as e:
        logger.warning(f"Failed to generate queries: {e}")
        queries = [state["research_goal"]]

    # ===========================================
    # phase 2: collect papers with fulltexts
    # ===========================================
    logger.info("Phase 2: collecting papers with pubmed_search_with_fulltext")

    # create slug for this research goal
    slug = "research_" + hashlib.md5(state["research_goal"].encode()).hexdigest()[:8]

    # distribute papers across queries to hit target count
    # calculate base papers per query, then distribute remainder
    papers_per_query = papers_to_read_count // len(queries)
    remainder = papers_to_read_count % len(queries)

    # ensure minimum of 2 per query for diversity
    if papers_per_query < 2:
        papers_per_query = 2
        logger.warning(
            f"Target {papers_to_read_count} papers with {len(queries)} queries gives <2 per query, using 2 minimum"
        )

    logger.info(
        f"Distributing {papers_to_read_count} papers: {papers_per_query} per query (+ {remainder} extra to reach target)"
    )

    # execute all pubmed searches in parallel
    logger.info(
        f"Executing {len(queries)} PubMed searches in parallel with recency filter (last {LITERATURE_REVIEW_RECENCY_YEARS} years)"
    )

    async def search_query(query: str, index: int) -> tuple[int, dict]:
        """Search single query and return (index, results)"""
        # distribute remainder across first N queries to hit target exactly
        query_papers = papers_per_query + (1 if index <= remainder else 0)
        logger.debug(
            f"searching with query {index}/{len(queries)} ({query_papers} papers): {query[:80]}..."
        )
        try:
            result = await mcp_client.call_tool(
                "pubmed_search_with_fulltext",
                query=query,
                slug=slug,
                max_papers=query_papers,
                recency_years=LITERATURE_REVIEW_RECENCY_YEARS,
                run_id=state["run_id"],
            )

            # parse result
            if isinstance(result, str):
                result_data = json.loads(result)
            else:
                result_data = result

            logger.debug(f"query {index}: found {len(result_data)} papers")
            return (index, result_data)

        except Exception as e:
            logger.error(f"Query {index} failed: {e}")
            return (index, {})

    # run all searches concurrently
    search_tasks = [search_query(query, i + 1) for i, query in enumerate(queries)]
    search_results = await asyncio.gather(*search_tasks)

    # merge all results
    all_paper_metadata = {}
    for index, result_data in search_results:
        all_paper_metadata.update(result_data)

    # log PMC fulltext availability
    papers_with_pmc = [
        pid for pid, meta in all_paper_metadata.items() if meta.get("pmc_full_text_id")
    ]
    papers_without_pmc = len(all_paper_metadata) - len(papers_with_pmc)
    logger.info(
        f"Collected {len(all_paper_metadata)} unique papers ({len(papers_with_pmc)} with PMC fulltext)"
    )

    if papers_without_pmc > 0:
        logger.warning(f"{papers_without_pmc} papers do not have PMC fulltexts")

    if len(papers_with_pmc) == 0:
        logger.error("No papers have PMC fulltexts - cannot perform PaperQA analysis")
        logger.info("Returning literature review failure - will fall back to standard generation")
        logger.info("Still creating article objects from metadata (abstracts available)")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_complete",
                {
                    "message": f"Literature review failed ({len(all_paper_metadata)} papers found but none have PMC fulltexts)",
                    "progress": 0.2,
                },
            )

        # still create article objects from metadata even though PaperQA can't run
        articles_no_fulltext = []
        for paper_id, metadata in all_paper_metadata.items():
            year = None
            if "date_revised" in metadata:
                try:
                    year_str = metadata["date_revised"].split("/")[0]
                    year = int(year_str)
                except (ValueError, KeyError, IndexError, AttributeError):
                    pass

            articles_no_fulltext.append(
                Article(
                    title=metadata.get("title", "unknown"),
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/",
                    authors=metadata.get("authors", []),
                    year=year,
                    venue=metadata.get("venue"),
                    abstract=metadata.get("abstract", ""),
                    source_id=paper_id,
                    source="pubmed",
                    content=None,
                    used_in_analysis=False,
                )
            )

        return {
            "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
            "literature_review_queries": queries,
            "articles": articles_no_fulltext,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"literature review failed: {len(all_paper_metadata)} papers found but none have PMC fulltexts for analysis",
                    "metadata": {"phase": "literature_review", "error": True},
                }
            ],
        }

    # log paper details for debugging
    for paper_id, meta in list(all_paper_metadata.items())[:3]:  # show first 3
        logger.debug(
            f"paper {paper_id}: title='{meta.get('title', '')[:60]}...' pmc_id={meta.get('pmc_full_text_id', 'NONE')}"
        )

    if len(all_paper_metadata) == 0:
        logger.warning("No papers collected - literature review failed")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_complete",
                {"message": "Literature review completed (no papers found)", "progress": 0.2},
            )

        return {
            "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
            "literature_review_queries": queries,
            "articles": [],
            "messages": [
                {
                    "role": "assistant",
                    "content": "completed literature review with 0 papers found",
                    "metadata": {"phase": "literature_review"},
                }
            ],
        }

    # ===========================================
    # phase 3: analyze each paper (parallel)
    # ===========================================
    logger.info("Phase 3: analyzing each paper for gaps, limitations, and future work")

    # check if papers have fulltext
    papers_with_fulltext = {
        pid: metadata for pid, metadata in all_paper_metadata.items() if metadata.get("fulltext")
    }

    if not papers_with_fulltext:
        logger.error("No papers have fulltext content - cannot perform analysis")
        logger.info("Creating article objects from metadata (abstracts available)")
        synthesis = LITERATURE_REVIEW_FAILED

        # skip to phase 5 to create articles
    else:
        logger.info(f"Analyzing {len(papers_with_fulltext)} papers with fulltext (parallel)")

        # analyze each paper in parallel
        async def analyze_paper(paper_id: str, metadata: dict) -> dict:
            """Analyze single paper for gaps and opportunities"""
            try:
                # get year from metadata
                year = None
                if "date_revised" in metadata:
                    try:
                        year_str = metadata["date_revised"].split("/")[0]
                        year = int(year_str)
                    except (ValueError, KeyError, IndexError, AttributeError):
                        pass

                # truncate fulltext if too long
                fulltext = metadata.get("fulltext", "")
                max_chars = 200_000
                if len(fulltext) > max_chars:
                    logger.debug(f"truncating paper {paper_id} fulltext to {max_chars} chars")
                    fulltext = fulltext[:max_chars] + "\n\n[... truncated for length ...]"

                # get analysis prompt
                prompt = get_literature_review_paper_analysis_prompt(
                    research_goal=state["research_goal"],
                    title=metadata.get("title", "Unknown"),
                    authors=metadata.get("authors", []),
                    year=year,
                    fulltext=fulltext,
                )

                # call llm for analysis
                analysis = await call_llm_json(
                    prompt=prompt,
                    model_name=state["model_name"],
                    json_schema=LITERATURE_PAPER_ANALYSIS_SCHEMA,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    temperature=HIGH_TEMPERATURE,
                )

                logger.debug(f"analyzed paper {paper_id}: {metadata.get('title', 'Unknown')[:60]}")

                return {"paper_id": paper_id, "metadata": metadata, "analysis": analysis}

            except Exception as e:
                logger.error(f"failed to analyze paper {paper_id}: {e}")
                return None

        # run analyses in parallel
        paper_analyses_tasks = [
            analyze_paper(paper_id, metadata) for paper_id, metadata in papers_with_fulltext.items()
        ]
        paper_analyses_results = await asyncio.gather(*paper_analyses_tasks)

        # filter out failed analyses
        paper_analyses = [r for r in paper_analyses_results if r is not None]
        logger.info(f"completed {len(paper_analyses)}/{len(papers_with_fulltext)} paper analyses")

        # debug: log structure of first analysis
        if paper_analyses:
            first_analysis = paper_analyses[0]
            logger.debug(
                f"sample analysis structure - has metadata: {'metadata' in first_analysis}, has analysis: {'analysis' in first_analysis}"
            )
            if "analysis" in first_analysis:
                analysis_keys = list(first_analysis["analysis"].keys())
                logger.debug(f"sample analysis fields: {analysis_keys}")

        if not paper_analyses:
            logger.error("all paper analyses failed - cannot create synthesis")
            synthesis = LITERATURE_REVIEW_FAILED
        else:
            # ===========================================
            # phase 4: synthesize across papers
            # ===========================================
            logger.info("Phase 4: synthesizing across papers to create articles_with_reasoning")

            try:
                # get synthesis prompt
                synthesis_prompt = get_literature_review_synthesis_prompt(
                    research_goal=state['research_goal'],
                    paper_analyses=paper_analyses
                )

                # write synthesis prompt to disk for debugging
                try:
                    run_id = state.get("run_id", "unknown")
                    prompts_output_dir = os.path.join(".coscientist_prompts", run_id)
                    os.makedirs(prompts_output_dir, exist_ok=True)
                    prompt_output_path = os.path.join(
                        prompts_output_dir, "literature_review_synthesis.txt"
                    )
                    with open(prompt_output_path, "w") as f:
                        f.write(synthesis_prompt)
                    logger.debug(f"wrote synthesis prompt to: {prompt_output_path}")
                except Exception as e:
                    logger.warning(f"failed to write synthesis prompt to disk: {e}")

                logger.info(
                    f"calling synthesis LLM with prompt length: {len(synthesis_prompt)} chars, {len(paper_analyses)} papers"
                )

                # call llm for synthesis (free-form markdown, needs more tokens for comprehensive output)
                synthesis = await call_llm(
                    prompt=synthesis_prompt,
                    model_name=state["model_name"],
                    max_tokens=EXTENDED_MAX_TOKENS,
                    temperature=HIGH_TEMPERATURE,
                )

                logger.info(f"synthesis complete - length: {len(synthesis)} chars")
                logger.debug(f"synthesis preview: {synthesis[:500]}...")

            except Exception as e:
                logger.error(f"synthesis failed: {e}")
                synthesis = LITERATURE_REVIEW_FAILED

    # ===========================================
    # phase 5: create article objects
    # ===========================================
    logger.info("Phase 5: creating article objects")

    articles = []
    for paper_id, metadata in all_paper_metadata.items():
        # parse year from date_revised if available
        year = None
        if "date_revised" in metadata:
            try:
                year_str = metadata["date_revised"].split("/")[0]
                year = int(year_str)
            except (ValueError, KeyError, IndexError, AttributeError):
                pass

        article = Article(
            title=metadata.get("title", "unknown"),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/",
            authors=metadata.get("authors", []),
            year=year,
            venue=metadata.get("publication"),
            citations=0,  # pubmed doesn't provide citation counts
            abstract=metadata.get("abstract"),
            content=None,  # fulltext is in pmc html files
            source_id=paper_id,
            source="pubmed",
            pdf_links=[],  # html-only implementation
            used_in_analysis=True,  # all collected papers that were analyzed
        )
        articles.append(article)

    logger.info(f"Created {len(articles)} article objects")

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "literature_review_complete",
            {
                "message": "Literature review completed",
                "progress": 0.2,
                "queries_count": len(queries),
                "articles_count": len(articles),
            },
        )

    logger.info(
        f"Literature review complete: {len(articles)} articles from {len(queries)} queries, {len(synthesis)} char synthesis"
    )

    result = {
        "articles_with_reasoning": synthesis,
        "literature_review_queries": queries,
        "articles": articles,
        "messages": [
            {
                "role": "assistant",
                "content": f"completed literature review with {len(queries)} queries, {len(articles)} articles analyzed",
                "metadata": {"phase": "literature_review"},
            }
        ],
    }

    # cache the result after successful completion
    node_cache.set("literature_review", result, force=force_cache, **cache_params)

    return result
