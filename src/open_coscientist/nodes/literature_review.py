"""
Literature review node.

- Check literature source availability via MCP
- Generate search queries with LLM
- Collect papers with configured search tool (e.g., pubmed_search_with_fulltext)
- Analyze each paper for gaps/limitations/future work
- Synthesize across papers to create articles_with_reasoning
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

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
from ..mcp_client import get_mcp_client, check_literature_source_available
from ..models import Article
from ..prompts import (
    get_literature_review_query_generation_pubmed_prompt,
    get_literature_review_paper_analysis_prompt,
    get_literature_review_synthesis_prompt,
)
from ..schemas import LITERATURE_QUERY_SCHEMA, LITERATURE_PAPER_ANALYSIS_SCHEMA
from ..state import WorkflowState

if TYPE_CHECKING:
    from ..config import ToolRegistry, ToolConfig, SearchSourceConfig

logger = logging.getLogger(__name__)


def _extract_source_name(tool_config: Optional["ToolConfig"]) -> str:
    """Extract source name from tool config's response_format field_mapping."""
    if not tool_config:
        return "unknown"
    if tool_config.response_format and tool_config.response_format.field_mapping:
        source_val = tool_config.response_format.field_mapping.get("source", "")
        if source_val.startswith("'") and source_val.endswith("'"):
            return source_val[1:-1]  # strip quotes from static value
    return tool_config.source_type or "unknown"


def _normalize_search_response(
    result_data: Any,
    tool_config: Optional["ToolConfig"],
) -> Dict[str, Dict[str, Any]]:
    """
    Normalize search tool response to standard {paper_id: metadata} format.

    Handles both PubMed-style dict responses and arXiv-style list responses.
    """
    if not isinstance(result_data, (dict, list)):
        return {}

    if not tool_config or not tool_config.response_format:
        # no config, assume PubMed-style dict response
        return result_data if isinstance(result_data, dict) else {}

    results_path = tool_config.response_format.results_path
    is_dict = tool_config.response_format.is_dict

    # extract results from nested path (e.g., "results")
    if results_path and results_path != ".":
        result_data = result_data.get(results_path, result_data) if isinstance(result_data, dict) else result_data

    if is_dict and isinstance(result_data, dict):
        # PubMed style: {paper_id: metadata}
        return result_data

    if isinstance(result_data, list):
        # arXiv style: list of papers - convert to dict keyed by source_id
        source_id_field = tool_config.response_format.field_mapping.get("source_id", "source_id")
        # handle special field mappings like "@key"
        if source_id_field.startswith("@"):
            source_id_field = "arxiv_id"  # fallback for list responses

        normalized = {}
        for paper in result_data:
            paper_id = (
                paper.get(source_id_field) or
                paper.get("arxiv_id") or
                paper.get("id") or
                str(len(normalized))
            )
            normalized[paper_id] = paper
        return normalized

    # unknown format
    return result_data if isinstance(result_data, dict) else {}


def _build_article_from_metadata(
    paper_id: str,
    metadata: Dict[str, Any],
    source_name: str = "pubmed",
    used_in_analysis: bool = True,
) -> Article:
    """
    Build an Article object from MCP response metadata.

    Uses URL from metadata if available, otherwise constructs default URL.
    Source name can be configured via tool_registry.

    Args:
        paper_id: Unique identifier for the paper
        metadata: Dict of paper metadata from MCP tool response
        source_name: Name of the literature source (default: pubmed for backwards compat)
        used_in_analysis: Whether this paper was used in the analysis phase
    """
    # parse year from date_revised if available
    year = None
    if "date_revised" in metadata:
        try:
            year_str = metadata["date_revised"].split("/")[0]
            year = int(year_str)
        except (ValueError, KeyError, IndexError, AttributeError):
            pass

    # use URL from metadata if available, else construct default
    url = metadata.get("url")
    if not url:
        # default URL construction based on source
        if source_name == "pubmed":
            url = f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"
        else:
            url = f"https://doi.org/{paper_id}" if paper_id.startswith("10.") else paper_id

    return Article(
        title=metadata.get("title", "unknown"),
        url=url,
        authors=metadata.get("authors", []),
        year=year,
        venue=metadata.get("publication") or metadata.get("venue"),
        citations=0,
        abstract=metadata.get("abstract"),
        content=metadata.get("fulltext"),
        source_id=paper_id,
        source=source_name,
        pdf_links=[],
        used_in_analysis=used_in_analysis,
    )


async def literature_review_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Conduct literature review using configured MCP tools with direct LLM analysis.

    Phase 1: generate search queries with LLM
    Phase 2: collect papers with fulltexts using configured search tool
    Phase 3: analyze each paper for gaps, limitations, future work (parallel)
    Phase 4: synthesize across papers to create articles_with_reasoning
    Phase 5: return results with article objects

    Args:
        state: Current workflow state (may contain tool_registry for config-driven tool selection)

    Returns:
        Dictionary with updated state fields
    """
    logger.info("Starting literature review node")

    # get tool registry from state (may be None for backwards compatibility)
    tool_registry = state.get("tool_registry")

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

    # get search configuration from registry
    # supports both single-source (primary_search) and multi-source (search_sources) modes
    workflow = tool_registry.get_workflow("literature_review") if tool_registry else None
    is_multi_source = workflow and workflow.is_multi_source()

    # for single-source mode: track the single search tool config
    search_tool_name = "pubmed_search_with_fulltext"  # default for backwards compat
    source_name = "pubmed"  # default for backwards compat
    search_tool_config = None

    if is_multi_source:
        enabled_sources = workflow.get_enabled_search_sources()
        source_names = [s.tool for s in enabled_sources]
        logger.info(f"Multi-source mode: {len(enabled_sources)} sources configured: {source_names}")
    elif tool_registry and workflow and workflow.primary_search:
        # single-source mode
        search_tool_config = tool_registry.get_tool(workflow.primary_search)
        if search_tool_config:
            search_tool_name = search_tool_config.mcp_tool_name
            source_name = _extract_source_name(search_tool_config)
            logger.info(f"Single-source mode: {search_tool_name} (source: {source_name})")

    # test if literature source is available via MCP
    source_available = await check_literature_source_available(tool_registry=tool_registry)
    if not source_available:
        logger.error("Literature source MCP service unavailable - literature review disabled")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_error",
                {"message": "Literature review failed (source unavailable)", "progress": 0.2},
            )

        return {
            "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
            "literature_review_queries": [],
            "articles": [],
            "messages": [
                {
                    "role": "assistant",
                    "content": "literature review failed - literature source service unavailable",
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
            {"message": "Conducting literature review...", "progress": 0.1},
        )

    # initialize mcp client
    mcp_client = await get_mcp_client(tool_registry=tool_registry)

    # get optional fields
    preferences = state.get("preferences", "")
    attributes = state.get("attributes", [])
    user_hypotheses = state.get("starting_hypotheses", [])
    user_literature = state.get("literature", [])

    # ===========================================
    # phase 1: generate search queries
    # ===========================================
    logger.info("Phase 1: generating search queries")

    # check if MCP-based query generation is configured
    query_gen_tool_name = None
    query_format = "boolean"  # default for PubMed
    if tool_registry:
        workflow = tool_registry.get_workflow("literature_review")
        if workflow and workflow.query_generation_tool:
            tool_config = tool_registry.get_tool(workflow.query_generation_tool)
            if tool_config:
                query_gen_tool_name = tool_config.mcp_tool_name
                query_format = workflow.query_format
                logger.info(f"Using MCP query generation: {query_gen_tool_name} (format: {query_format})")

    queries = []

    if query_gen_tool_name:
        # use MCP tool for query generation
        try:
            result = await mcp_client.call_tool(
                query_gen_tool_name,
                research_goal=state["research_goal"],
                query_format=query_format,
            )

            # parse result (should be a list of queries)
            if isinstance(result, str):
                result_data = json.loads(result)
                queries = result_data if isinstance(result_data, list) else result_data.get("queries", [])
            elif isinstance(result, list):
                queries = result
            else:
                queries = []

            logger.info(f"MCP query generation returned {len(queries)} queries")

        except Exception as e:
            logger.warning(f"MCP query generation failed: {e}, falling back to LLM")
            query_gen_tool_name = None  # trigger fallback

    if not queries:
        # fallback to LLM-based query generation (default for PubMed)
        query_generation_prompt = get_literature_review_query_generation_pubmed_prompt(
            research_goal=state["research_goal"],
            preferences=preferences,
            attributes=attributes,
            user_literature=user_literature,
            user_hypotheses=user_hypotheses,
        )

        try:
            queries_json = await call_llm_json(
                prompt=query_generation_prompt,
                model_name=state["model_name"],
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=HIGH_TEMPERATURE,
                json_schema=LITERATURE_QUERY_SCHEMA,
            )

            queries = queries_json.get("queries", [])

        except Exception as e:
            logger.warning(f"LLM query generation failed: {e}")

    # fallback to research goal if no queries generated
    if not queries:
        logger.warning("No queries generated, using research goal")
        queries = [state["research_goal"]]

    # limit to 3 queries max
    queries = queries[:3]

    logger.info(f"Generated {len(queries)} search queries")
    for i, q in enumerate(queries, 1):
        logger.debug(f"query {i}: {q}")

    # ===========================================
    # phase 2: collect papers with fulltexts
    # ===========================================
    # create slug for this research goal
    slug = "research_" + hashlib.md5(state["research_goal"].encode()).hexdigest()[:8]

    # paper_source_map tracks which source each paper came from (for content retrieval)
    paper_source_map: Dict[str, str] = {}  # paper_id -> source_tool_id
    all_paper_metadata: Dict[str, Dict[str, Any]] = {}

    if is_multi_source:
        # ===========================================
        # multi-source mode: search each source with configured papers_per_query
        # ===========================================
        enabled_sources = workflow.get_enabled_search_sources()
        logger.info(f"Phase 2: collecting papers from {len(enabled_sources)} sources")

        async def search_source(
            source_config: "SearchSourceConfig",
            queries: List[str],
        ) -> Tuple[str, Dict[str, Dict[str, Any]]]:
            """Search a single source with all queries, return (source_tool_id, results)."""
            tool_config = tool_registry.get_tool(source_config.tool)
            if not tool_config:
                logger.warning(f"Tool config not found for source: {source_config.tool}")
                return (source_config.tool, {})

            mcp_tool_name = tool_config.mcp_tool_name
            src_name = _extract_source_name(tool_config)
            papers_per_query = source_config.papers_per_query

            logger.info(
                f"Searching {src_name} ({mcp_tool_name}): {papers_per_query} papers/query × {len(queries)} queries"
            )

            source_results = {}
            for query in queries:
                try:
                    canonical_params = {
                        "query": query,
                        "slug": slug,
                        "max_papers": papers_per_query,
                        "recency_years": LITERATURE_REVIEW_RECENCY_YEARS,
                        "run_id": state["run_id"],
                    }
                    tool_params = tool_config.map_parameters(canonical_params)
                    tool_params = {k: v for k, v in tool_params.items() if v is not None}

                    result = await mcp_client.call_tool(mcp_tool_name, **tool_params)
                    result_data = json.loads(result) if isinstance(result, str) else result
                    normalized = _normalize_search_response(result_data, tool_config)

                    # tag each paper with source name
                    for pid, meta in normalized.items():
                        if isinstance(meta, dict):
                            meta["_source_name"] = src_name
                    source_results.update(normalized)

                except Exception as e:
                    logger.error(f"Query failed for {src_name}: {e}")

            logger.info(f"Source {src_name}: collected {len(source_results)} papers")
            return (source_config.tool, source_results)

        # run all source searches in parallel
        source_tasks = [search_source(src, queries) for src in enabled_sources]
        source_results = await asyncio.gather(*source_tasks)

        # merge results from all sources
        seen_titles = set()  # for deduplication
        for source_tool_id, results in source_results:
            for paper_id, metadata in results.items():
                # deduplication by title (case-insensitive)
                if workflow.deduplicate_across_sources and isinstance(metadata, dict):
                    title = (metadata.get("title") or "").lower().strip()
                    if title and title in seen_titles:
                        logger.debug(f"Skipping duplicate: {title[:60]}...")
                        continue
                    if title:
                        seen_titles.add(title)

                all_paper_metadata[paper_id] = metadata
                paper_source_map[paper_id] = source_tool_id

        logger.info(
            f"Multi-source search complete: {len(all_paper_metadata)} unique papers from {len(enabled_sources)} sources"
        )

    else:
        # ===========================================
        # single-source mode (legacy): distribute papers across queries
        # ===========================================
        logger.info(f"Phase 2: collecting papers with {search_tool_name}")

        # distribute papers across queries to hit target count
        papers_per_query = papers_to_read_count // len(queries)
        remainder = papers_to_read_count % len(queries)

        if papers_per_query < 2:
            papers_per_query = 2
            logger.warning(
                f"Target {papers_to_read_count} papers with {len(queries)} queries gives <2 per query, using 2 minimum"
            )

        logger.info(
            f"Distributing {papers_to_read_count} papers: {papers_per_query} per query (+ {remainder} extra)"
        )

        async def search_query(query: str, index: int) -> Tuple[int, Dict]:
            """Search single query and return (index, results)."""
            query_papers = papers_per_query + (1 if index <= remainder else 0)
            logger.debug(f"searching query {index}/{len(queries)} ({query_papers} papers): {query[:80]}...")

            try:
                canonical_params = {
                    "query": query,
                    "slug": slug,
                    "max_papers": query_papers,
                    "recency_years": LITERATURE_REVIEW_RECENCY_YEARS,
                    "run_id": state["run_id"],
                }

                if search_tool_config:
                    tool_params = search_tool_config.map_parameters(canonical_params)
                    tool_params = {k: v for k, v in tool_params.items() if v is not None}
                else:
                    tool_params = canonical_params

                result = await mcp_client.call_tool(search_tool_name, **tool_params)
                result_data = json.loads(result) if isinstance(result, str) else result
                normalized = _normalize_search_response(result_data, search_tool_config)

                logger.debug(f"query {index}: found {len(normalized)} papers")
                return (index, normalized)

            except Exception as e:
                logger.error(f"Query {index} failed: {e}")
                return (index, {})

        # run all searches concurrently
        search_tasks = [search_query(query, i + 1) for i, query in enumerate(queries)]
        search_results = await asyncio.gather(*search_tasks)

        # merge all results
        for index, result_data in search_results:
            all_paper_metadata.update(result_data)

    # ===========================================
    # phase 2.5: fetch content for papers with pdf_url but no fulltext
    # ===========================================
    # build content retrieval config per source (handles both single and multi-source modes)
    # format: {source_tool_id: (content_tool_mcp_name, url_field)}
    content_config_by_source: Dict[str, Tuple[str, str]] = {}

    if is_multi_source and tool_registry:
        # multi-source: check per-source content_tool, fall back to workflow-level
        workflow_content_tool = workflow.content_tool
        workflow_url_field = workflow.content_url_field

        for source in workflow.get_enabled_search_sources():
            # per-source override or workflow-level fallback
            src_content_tool = source.content_tool or workflow_content_tool
            src_url_field = source.content_url_field or workflow_url_field

            if src_content_tool:
                tool_cfg = tool_registry.get_tool(src_content_tool)
                if tool_cfg:
                    content_config_by_source[source.tool] = (tool_cfg.mcp_tool_name, src_url_field)

        if content_config_by_source:
            logger.info(f"Content retrieval configured for {len(content_config_by_source)} sources")

    elif tool_registry and workflow and workflow.content_tool:
        # single-source: use workflow-level content_tool for all papers
        content_tool_cfg = tool_registry.get_tool(workflow.content_tool)
        if content_tool_cfg:
            # use a special key for single-source mode
            content_config_by_source["_default"] = (
                content_tool_cfg.mcp_tool_name,
                workflow.content_url_field,
            )
            logger.info(
                f"Content retrieval configured: {content_tool_cfg.mcp_tool_name} using {workflow.content_url_field}"
            )

    if content_config_by_source:
        # identify papers that need content retrieval
        papers_needing_content = []
        for pid, meta in all_paper_metadata.items():
            if not isinstance(meta, dict) or meta.get("fulltext"):
                continue

            # determine which content config to use for this paper
            source_tool_id = paper_source_map.get(pid, "_default")
            config = content_config_by_source.get(source_tool_id) or content_config_by_source.get("_default")
            if not config:
                continue

            content_tool_mcp_name, url_field = config
            content_url = meta.get(url_field)
            if content_url:
                papers_needing_content.append((pid, meta, content_tool_mcp_name, url_field))

        if papers_needing_content:
            logger.info(f"Phase 2.5: fetching content for {len(papers_needing_content)} papers")

            async def fetch_paper_content(
                paper_id: str,
                metadata: dict,
                tool_name: str,
                url_field: str,
            ) -> Tuple[str, Optional[str]]:
                """Fetch PDF content for a single paper."""
                content_url = metadata.get(url_field)
                if not content_url:
                    return (paper_id, None)

                try:
                    logger.debug(f"Fetching content for {paper_id} via {tool_name}: {content_url}")
                    result = await mcp_client.call_tool(tool_name, url=content_url)

                    # parse result (may be string or dict with content field)
                    if isinstance(result, str):
                        try:
                            result_data = json.loads(result)
                            content = result_data.get("content") or result_data.get("text") or result
                        except json.JSONDecodeError:
                            content = result
                    elif isinstance(result, dict):
                        content = result.get("content") or result.get("text") or str(result)
                    else:
                        content = str(result) if result else None

                    if content:
                        logger.debug(f"Retrieved {len(content)} chars for paper {paper_id}")
                    return (paper_id, content)

                except Exception as e:
                    logger.warning(f"Failed to fetch content for {paper_id}: {e}")
                    return (paper_id, None)

            # fetch content in parallel
            fetch_tasks = [
                fetch_paper_content(pid, meta, tool_name, url_field)
                for pid, meta, tool_name, url_field in papers_needing_content
            ]
            fetch_results = await asyncio.gather(*fetch_tasks)

            # update metadata with fetched content
            content_fetched_count = 0
            for paper_id, content in fetch_results:
                if content and paper_id in all_paper_metadata:
                    all_paper_metadata[paper_id]["fulltext"] = content
                    content_fetched_count += 1

            logger.info(
                f"Content retrieval complete: {content_fetched_count}/{len(papers_needing_content)} papers"
            )

    # log fulltext availability (check multiple possible indicators)
    # PubMed uses: pmc_full_text_id, fulltext
    # arXiv uses: pdf_url (all arXiv papers have PDFs)
    papers_with_fulltext_indicator = [
        pid for pid, meta in all_paper_metadata.items()
        if isinstance(meta, dict) and (
            meta.get("pmc_full_text_id") or
            meta.get("fulltext") or
            meta.get("has_fulltext") or
            meta.get("pdf_url")  # arXiv papers all have PDF URLs
        )
    ]
    papers_without_fulltext = len(all_paper_metadata) - len(papers_with_fulltext_indicator)
    logger.info(
        f"Collected {len(all_paper_metadata)} unique papers ({len(papers_with_fulltext_indicator)} with fulltext)"
    )

    if papers_without_fulltext > 0:
        logger.warning(f"{papers_without_fulltext} papers do not have fulltexts available")

    if len(papers_with_fulltext_indicator) == 0:
        logger.error("No papers have fulltexts available - cannot perform analysis")
        logger.info("Returning literature review failure - will fall back to standard generation")
        logger.info("Still creating article objects from metadata (abstracts available)")

        if state.get("progress_callback"):
            await state["progress_callback"](
                "literature_review_complete",
                {
                    "message": f"Literature review failed ({len(all_paper_metadata)} papers found but none have fulltexts)",
                    "progress": 0.2,
                },
            )

        # still create article objects from metadata even though fulltext analysis can't run
        articles_no_fulltext = [
            _build_article_from_metadata(paper_id, metadata, source_name, used_in_analysis=False)
            for paper_id, metadata in all_paper_metadata.items()
        ]

        return {
            "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
            "literature_review_queries": queries,
            "articles": articles_no_fulltext,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"literature review failed: {len(all_paper_metadata)} papers found but none have fulltexts for analysis",
                    "metadata": {"phase": "literature_review", "error": True},
                }
            ],
        }

    # log paper details for debugging
    for paper_id, meta in list(all_paper_metadata.items())[:3]:  # show first 3
        has_fulltext = bool(meta.get("pmc_full_text_id") or meta.get("fulltext") or meta.get("pdf_url"))
        logger.debug(
            f"paper {paper_id}: title='{meta.get('title', '')[:60]}...' has_fulltext={has_fulltext}"
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

    # check if papers have content for analysis
    # PubMed: fulltext field contains actual content
    # arXiv: pdf_url exists but content not downloaded - use abstract as fallback
    papers_with_content = {}
    for pid, metadata in all_paper_metadata.items():
        if not isinstance(metadata, dict):
            continue
        if metadata.get("fulltext"):
            # has actual fulltext content
            papers_with_content[pid] = metadata
        elif metadata.get("pdf_url") and metadata.get("abstract"):
            # arXiv-style: has PDF URL and abstract - use abstract for analysis
            papers_with_content[pid] = metadata
            logger.debug(f"Paper {pid}: using abstract for analysis (fulltext not downloaded)")

    if not papers_with_content:
        logger.error("No papers have content for analysis")
        logger.info("Creating article objects from metadata (abstracts available)")
        synthesis = LITERATURE_REVIEW_FAILED

        # skip to phase 5 to create articles
    else:
        logger.info(f"Analyzing {len(papers_with_content)} papers with content (parallel)")

        # analyze each paper in parallel
        async def analyze_paper(paper_id: str, metadata: dict) -> dict:
            """Analyze single paper for gaps and opportunities"""
            try:
                # get year from metadata (supports both PubMed and arXiv formats)
                year = metadata.get("year")
                if not year and "date_revised" in metadata:
                    try:
                        year_str = metadata["date_revised"].split("/")[0]
                        year = int(year_str)
                    except (ValueError, KeyError, IndexError, AttributeError):
                        pass

                # use fulltext if available, otherwise fall back to abstract
                fulltext = metadata.get("fulltext") or metadata.get("abstract") or ""
                max_chars = 200_000
                if len(fulltext) > max_chars:
                    logger.debug(f"truncating paper {paper_id} content to {max_chars} chars")
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
            analyze_paper(paper_id, metadata) for paper_id, metadata in papers_with_content.items()
        ]
        paper_analyses_results = await asyncio.gather(*paper_analyses_tasks)

        # filter out failed analyses
        paper_analyses = [r for r in paper_analyses_results if r is not None]
        logger.info(f"completed {len(paper_analyses)}/{len(papers_with_content)} paper analyses")

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
                    research_goal=state["research_goal"], paper_analyses=paper_analyses
                )

                # save synthesis prompt to disk for debugging
                from ..prompts import save_prompt_to_disk

                save_prompt_to_disk(
                    run_id=state.get("run_id", "unknown"),
                    prompt_name="literature_review_synthesis",
                    content=synthesis_prompt,
                    metadata={
                        "prompt_length_chars": len(synthesis_prompt),
                        "papers_analyzed": len(paper_analyses),
                    },
                )

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
        # in multi-source mode, use per-paper source name; otherwise use single source_name
        paper_source = metadata.get("_source_name", source_name) if isinstance(metadata, dict) else source_name
        articles.append(
            _build_article_from_metadata(paper_id, metadata, paper_source, used_in_analysis=True)
        )

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
