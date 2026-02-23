"""
Literature review node.

Orchestrates a multi-phase literature review process:
1. Generate search queries (MCP tool or LLM)
2. Collect papers from configured sources
3. Discover PDF links (for sources returning landing pages)
4. Fetch content (for sources without fulltext)
5. Analyze each paper for gaps/limitations
6. Synthesize findings into articles_with_reasoning
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
from ..mcp_client import get_mcp_client, check_literature_source_available, MCPToolClient
from ..models import Article
from ..prompts import (
    get_literature_review_query_generation_prompt,
    get_literature_review_paper_analysis_prompt,
    get_literature_review_synthesis_prompt,
    save_prompt_to_disk,
)
from ..schemas import LITERATURE_QUERY_SCHEMA, LITERATURE_PAPER_ANALYSIS_SCHEMA
from ..state import WorkflowState

from .reflection_helpers import extract_entity_names
from .literature_review_helpers import (
    SearchConfig,
    ContentToolConfig,
    extract_source_name,
    normalize_search_response,
    build_articles_from_metadata,
    count_papers_with_fulltext,
    get_papers_with_content,
    make_failure_result,
    make_success_result,
    emit_progress,
    parse_mcp_query_result,
    determine_query_source_type,
    calculate_papers_per_query,
    merge_search_results,
    build_pdf_discovery_config,
    get_papers_needing_pdf_discovery,
    parse_pdf_discovery_result,
    build_content_config,
    get_papers_needing_content,
    parse_content_result,
    get_paper_content_for_analysis,
)

if TYPE_CHECKING:
    from ..config import ToolRegistry, ToolConfig, SearchSourceConfig, WorkflowConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration setup
# =============================================================================


def _get_search_config(state: WorkflowState) -> SearchConfig:
    """Extract search configuration from state and tool registry."""
    tool_registry = state.get("tool_registry")
    workflow = tool_registry.get_workflow("literature_review") if tool_registry else None
    is_multi_source = workflow and workflow.is_multi_source()

    # defaults for backwards compatibility
    search_tool_name = "pubmed_search_with_fulltext"
    source_name = "pubmed"
    search_tool_config = None

    if is_multi_source:
        enabled_sources = workflow.get_enabled_search_sources()
        source_names = [s.tool for s in enabled_sources]
        logger.info(f"Multi-source mode: {len(enabled_sources)} sources configured: {source_names}")
    elif tool_registry and workflow and workflow.primary_search:
        search_tool_config = tool_registry.get_tool(workflow.primary_search)
        if search_tool_config:
            search_tool_name = search_tool_config.mcp_tool_name
            source_name = extract_source_name(search_tool_config)
            logger.info(f"Single-source mode: {search_tool_name} (source: {source_name})")

    # dev mode detection
    is_dev_mode = os.getenv("COSCIENTIST_DEV_MODE", "false").lower() in ("true", "1", "yes")
    papers_to_read_count = (
        LITERATURE_REVIEW_PAPERS_COUNT_DEV if is_dev_mode else LITERATURE_REVIEW_PAPERS_COUNT
    )

    return SearchConfig(
        tool_registry=tool_registry,
        workflow=workflow,
        is_multi_source=is_multi_source,
        search_tool_name=search_tool_name,
        search_tool_config=search_tool_config,
        source_name=source_name,
        papers_to_read_count=papers_to_read_count,
        is_dev_mode=is_dev_mode,
    )


# =============================================================================
# Phase 1: Query generation
# =============================================================================


async def _generate_queries_via_mcp(
    mcp_client: MCPToolClient,
    research_goal: str,
    tool_name: str,
    query_format: str,
) -> List[str]:
    """Generate queries using MCP tool."""
    try:
        result = await mcp_client.call_tool(
            tool_name,
            research_goal=research_goal,
            query_format=query_format,
        )
        queries = parse_mcp_query_result(result)
        logger.info(f"MCP query generation returned {len(queries)} queries")
        return queries
    except Exception as e:
        logger.warning(f"MCP query generation failed: {e}, falling back to LLM")
        return []


async def _generate_queries_via_llm(
    state: WorkflowState,
    config: SearchConfig,
) -> List[str]:
    """Generate queries using LLM with source-aware prompt."""
    source_type = determine_query_source_type(
        config.workflow,
        config.tool_registry,
        config.search_tool_config,
        config.is_multi_source,
    )
    logger.debug(f"Using {source_type} query generation prompt")

    prompt = get_literature_review_query_generation_prompt(
        research_goal=state["research_goal"],
        source_type=source_type,
        preferences=state.get("preferences", ""),
        attributes=state.get("attributes", []),
        user_literature=state.get("literature", []),
        user_hypotheses=state.get("starting_hypotheses", []),
    )

    try:
        result = await call_llm_json(
            prompt=prompt,
            model_name=state["model_name"],
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=HIGH_TEMPERATURE,
            json_schema=LITERATURE_QUERY_SCHEMA,
        )
        return result.get("queries", [])
    except Exception as e:
        logger.warning(f"LLM query generation failed: {e}")
        return []


async def _phase1_generate_queries(
    state: WorkflowState,
    config: SearchConfig,
    mcp_client: MCPToolClient,
) -> List[str]:
    """Phase 1: Generate search queries."""
    logger.info("Phase 1: generating search queries")

    queries = []

    # try MCP-based generation first if configured
    if config.tool_registry and config.workflow and config.workflow.query_generation_tool:
        tool_cfg = config.tool_registry.get_tool(config.workflow.query_generation_tool)
        if tool_cfg:
            query_format = config.workflow.query_format or "boolean"
            logger.info(f"Using MCP query generation: {tool_cfg.mcp_tool_name} (format: {query_format})")
            queries = await _generate_queries_via_mcp(
                mcp_client,
                state["research_goal"],
                tool_cfg.mcp_tool_name,
                query_format,
            )

    # fallback to LLM-based generation
    if not queries:
        queries = await _generate_queries_via_llm(state, config)

    # final fallback to research goal
    if not queries:
        logger.warning("No queries generated, using research goal")
        queries = [state["research_goal"]]

    # limit to 3 queries max
    queries = queries[:3]

    logger.info(f"Generated {len(queries)} search queries")
    for i, q in enumerate(queries, 1):
        logger.debug(f"Query {i}: {q}")

    return queries


# =============================================================================
# Phase 2: Paper collection
# =============================================================================


async def _search_single_source(
    source_config: "SearchSourceConfig",
    queries: List[str],
    slug: str,
    run_id: str,
    tool_registry: "ToolRegistry",
    mcp_client: MCPToolClient,
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """Search a single source with all queries."""
    tool_config = tool_registry.get_tool(source_config.tool)
    if not tool_config:
        logger.warning(f"Tool config not found for source: {source_config.tool}")
        return (source_config.tool, {})

    mcp_tool_name = tool_config.mcp_tool_name
    src_name = extract_source_name(tool_config)
    papers_per_query = source_config.papers_per_query

    logger.info(f"Searching {src_name} ({mcp_tool_name}): {papers_per_query} papers/query")

    source_results = {}
    for query in queries:
        try:
            canonical_params = {
                "query": query,
                "slug": slug,
                "max_papers": papers_per_query,
                "recency_years": LITERATURE_REVIEW_RECENCY_YEARS,
                "run_id": run_id,
            }
            tool_params = tool_config.map_parameters(canonical_params)
            tool_params = {k: v for k, v in tool_params.items() if v is not None}

            result = await mcp_client.call_tool(mcp_tool_name, **tool_params)
            result_data = json.loads(result) if isinstance(result, str) else result
            normalized = normalize_search_response(result_data, tool_config)

            for pid, meta in normalized.items():
                if isinstance(meta, dict):
                    meta["_source_name"] = src_name
            source_results.update(normalized)

        except Exception as e:
            logger.error(f"Query failed for {src_name}: {e}")

    logger.info(f"Source {src_name}: collected {len(source_results)} papers")
    return (source_config.tool, source_results)


async def _search_single_query(
    query: str,
    index: int,
    papers_count: int,
    slug: str,
    run_id: str,
    search_tool_name: str,
    search_tool_config: Optional["ToolConfig"],
    mcp_client: MCPToolClient,
) -> Tuple[int, Dict[str, Dict[str, Any]]]:
    """Search single query (for single-source mode)."""
    logger.debug(f"Searching query {index} ({papers_count} papers): {query[:80]}...")

    try:
        canonical_params = {
            "query": query,
            "slug": slug,
            "max_papers": papers_count,
            "recency_years": LITERATURE_REVIEW_RECENCY_YEARS,
            "run_id": run_id,
        }

        if search_tool_config:
            tool_params = search_tool_config.map_parameters(canonical_params)
            tool_params = {k: v for k, v in tool_params.items() if v is not None}
        else:
            tool_params = canonical_params

        result = await mcp_client.call_tool(search_tool_name, **tool_params)
        result_data = json.loads(result) if isinstance(result, str) else result
        normalized = normalize_search_response(result_data, search_tool_config)

        logger.debug(f"Query {index}: found {len(normalized)} papers")
        return (index, normalized)

    except Exception as e:
        logger.error(f"Query {index} failed: {e}")
        return (index, {})


async def _phase2_collect_papers_multi_source(
    queries: List[str],
    slug: str,
    state: WorkflowState,
    config: SearchConfig,
    mcp_client: MCPToolClient,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Phase 2 (multi-source): Collect papers from multiple sources in parallel."""
    enabled_sources = config.workflow.get_enabled_search_sources()
    logger.info(f"Phase 2: collecting papers from {len(enabled_sources)} sources")

    # search all sources in parallel
    tasks = [
        _search_single_source(
            source,
            queries,
            slug,
            state["run_id"],
            config.tool_registry,
            mcp_client,
        )
        for source in enabled_sources
    ]
    source_results = await asyncio.gather(*tasks)

    # merge results
    all_paper_metadata, paper_source_map = merge_search_results(
        source_results,
        deduplicate=config.workflow.deduplicate_across_sources,
    )

    logger.info(
        f"Multi-source search complete: {len(all_paper_metadata)} unique papers "
        f"from {len(enabled_sources)} sources"
    )

    return all_paper_metadata, paper_source_map


async def _phase2_collect_papers_single_source(
    queries: List[str],
    slug: str,
    state: WorkflowState,
    config: SearchConfig,
    mcp_client: MCPToolClient,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Phase 2 (single-source): Collect papers with legacy distribution."""
    logger.info(f"Phase 2: collecting papers with {config.search_tool_name}")

    papers_per_query, remainder = calculate_papers_per_query(
        config.papers_to_read_count,
        len(queries),
    )

    logger.info(
        f"Distributing {config.papers_to_read_count} papers: "
        f"{papers_per_query} per query (+ {remainder} extra)"
    )

    # search all queries in parallel
    tasks = [
        _search_single_query(
            query,
            i + 1,
            papers_per_query + (1 if i < remainder else 0),
            slug,
            state["run_id"],
            config.search_tool_name,
            config.search_tool_config,
            mcp_client,
        )
        for i, query in enumerate(queries)
    ]
    search_results = await asyncio.gather(*tasks)

    # merge results (no source tracking needed for single-source)
    all_paper_metadata = {}
    for index, result_data in search_results:
        all_paper_metadata.update(result_data)

    return all_paper_metadata, {}


# =============================================================================
# Phase 2.4: PDF discovery
# =============================================================================


async def _discover_pdf_link(
    paper_id: str,
    metadata: Dict[str, Any],
    tool_name: str,
    url_field: str,
    mcp_client: MCPToolClient,
) -> Tuple[str, Optional[str]]:
    """Discover PDF link for a single paper."""
    landing_url = metadata.get(url_field)
    if not landing_url:
        return (paper_id, None)

    try:
        logger.debug(f"Discovering PDF links for {paper_id}: {landing_url}")
        result = await mcp_client.call_tool(tool_name, url=landing_url)
        pdf_url = parse_pdf_discovery_result(result)
        if pdf_url:
            logger.debug(f"Found PDF link for {paper_id}: {pdf_url}")
        return (paper_id, pdf_url)
    except Exception as e:
        logger.warning(f"Failed to discover PDF links for {paper_id}: {e}")
        return (paper_id, None)


async def _phase2_4_discover_pdf_links(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    paper_source_map: Dict[str, str],
    config: SearchConfig,
    mcp_client: MCPToolClient,
) -> None:
    """Phase 2.4: Discover PDF links for papers with landing pages."""
    pdf_discovery_config = build_pdf_discovery_config(
        config.workflow,
        config.tool_registry,
        config.is_multi_source,
    )

    if not pdf_discovery_config:
        return

    papers_needing_discovery = get_papers_needing_pdf_discovery(
        all_paper_metadata,
        paper_source_map,
        pdf_discovery_config,
    )

    if not papers_needing_discovery:
        return

    logger.info(f"Phase 2.4: discovering PDF links for {len(papers_needing_discovery)} papers")

    # discover in parallel
    tasks = [
        _discover_pdf_link(pid, meta, tool_name, url_field, mcp_client)
        for pid, meta, tool_name, url_field in papers_needing_discovery
    ]
    results = await asyncio.gather(*tasks)

    # update metadata
    discovered_count = 0
    for paper_id, pdf_url in results:
        if pdf_url and paper_id in all_paper_metadata:
            all_paper_metadata[paper_id]["pdf_url"] = pdf_url
            discovered_count += 1

    logger.info(f"PDF discovery complete: {discovered_count}/{len(papers_needing_discovery)} papers")


# =============================================================================
# Phase 2.5: Content fetching
# =============================================================================


async def _fetch_paper_content(
    paper_id: str,
    metadata: Dict[str, Any],
    content_cfg: "ContentToolConfig",
    mcp_client: MCPToolClient,
    runtime_context: Dict[str, Any],
) -> Tuple[str, Optional[str]]:
    """Fetch content for a single paper."""
    from ..config.schema import resolve_content_params

    content_url = metadata.get(content_cfg.url_field)
    if not content_url:
        return (paper_id, None)

    try:
        # resolve content_params with runtime context
        resolved_params = resolve_content_params(content_cfg.content_params, runtime_context)

        # build tool call args: url is always required, add any resolved params
        tool_args = {"url": content_url, **resolved_params}

        logger.debug(f"Fetching content for {paper_id} via {content_cfg.mcp_tool_name}: {content_url}")
        if resolved_params:
            logger.debug(f"  with params: {list(resolved_params.keys())}")

        result = await mcp_client.call_tool(content_cfg.mcp_tool_name, **tool_args)
        content = parse_content_result(result)
        if content:
            logger.debug(f"Retrieved {len(content)} chars for paper {paper_id}")
        return (paper_id, content)
    except Exception as e:
        logger.warning(f"Failed to fetch content for {paper_id}: {e}")
        return (paper_id, None)


async def _phase2_5_fetch_content(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    paper_source_map: Dict[str, str],
    config: SearchConfig,
    mcp_client: MCPToolClient,
    state: "WorkflowState",
) -> None:
    """Phase 2.5: Fetch content for papers with pdf_url but no fulltext."""
    content_config = build_content_config(
        config.workflow,
        config.tool_registry,
        config.is_multi_source,
    )

    if not content_config:
        return

    if content_config:
        logger.info(f"Content retrieval configured for {len(content_config)} source(s)")

    papers_needing_content = get_papers_needing_content(
        all_paper_metadata,
        paper_source_map,
        content_config,
    )

    if not papers_needing_content:
        return

    logger.info(f"Phase 2.5: fetching content for {len(papers_needing_content)} papers")

    # build runtime context for param resolution
    runtime_context = {
        "research_goal": state.get("research_goal", ""),
        "focus_areas": [],  # could be extracted from hypothesis categories later
    }

    # fetch in parallel
    tasks = [
        _fetch_paper_content(pid, meta, content_cfg, mcp_client, runtime_context)
        for pid, meta, content_cfg in papers_needing_content
    ]
    results = await asyncio.gather(*tasks)

    # update metadata
    fetched_count = 0
    for paper_id, content in results:
        if content and paper_id in all_paper_metadata:
            all_paper_metadata[paper_id]["fulltext"] = content
            fetched_count += 1

    logger.info(f"Content retrieval complete: {fetched_count}/{len(papers_needing_content)} papers")


# =============================================================================
# Phase 2.6: Context enrichment (knowledge-graph / external tools)
# =============================================================================

# max chars injected into synthesis prompt from all enrichment tools combined
_CONTEXT_ENRICHMENT_MAX_CHARS = 1500
# max results requested per entity per tool call
_CONTEXT_ENRICHMENT_RESULTS_PER_ENTITY = 4


async def _call_enrichment_tool_for_entity(
    tool_name: str,
    mapped_params: Dict[str, Any],
    mcp_client: MCPToolClient,
) -> Any:
    """Call one enrichment tool for one entity; returns raw result or None."""
    try:
        return await mcp_client.call_tool(tool_name, **mapped_params)
    except Exception as e:
        logger.debug(f"context enrichment call failed ({tool_name}): {e}")
        return None


def _parse_enrichment_result(raw: Any) -> tuple[str, List[Dict[str, Any]]]:
    """Extract formatted text AND structured items from an enrichment tool result.

    Returns (display_text, structured_items) where structured_items is a list
    of dicts suitable for storage in context_enrichment_sources.
    """
    import json as _json

    data = raw
    if isinstance(raw, str):
        try:
            data = _json.loads(raw)
        except (ValueError, TypeError):
            text = raw[:300] if raw else ""
            return text, [{"display": text, "data": {}}] if text else []

    if isinstance(data, dict):
        # INDRA-shaped response: has a "statements" key (even when empty).
        # Never fall through to the raw-dict repr for this format.
        if "statements" in data:
            stmts = data.get("statements", [])
            if not stmts:
                return "", []  # entity had no results - skip cleanly
            lines = []
            items = []
            for s in stmts[:_CONTEXT_ENRICHMENT_RESULTS_PER_ENTITY]:
                subj = (s.get("subj") or {}).get("name", "")
                obj = (s.get("obj") or {}).get("name", "")
                rel = s.get("type", "")
                belief = s.get("belief", 0)
                if subj and obj:
                    display = f"{subj} \u2192 {obj} [{rel}] (belief: {belief:.2f})"
                    lines.append(f"- {display}")
                    items.append({"display": f"INDRA: {display}", "data": s})
            return "\n".join(lines), items

        results = data.get("results", [])
        if results:
            capped = results[:_CONTEXT_ENRICHMENT_RESULTS_PER_ENTITY]
            text = "\n".join(str(r)[:120] for r in capped)
            items = [{"display": str(r)[:120], "data": r if isinstance(r, dict) else {}} for r in capped]
            return text, items

        text = str(data)[:300]
        return text, [{"display": text, "data": data}] if text else []

    if isinstance(data, list):
        capped = data[:_CONTEXT_ENRICHMENT_RESULTS_PER_ENTITY]
        text = "\n".join(str(item)[:120] for item in capped)
        items = [{"display": str(item)[:120], "data": item if isinstance(item, dict) else {}} for item in capped]
        return text, items

    text = str(data)[:300] if data else ""
    return text, [{"display": text, "data": {}}] if text else []


async def _call_enrichment_tool_for_entities(
    tool_config: Any,
    entities: List[str],
    mcp_client: MCPToolClient,
) -> tuple[str, List[Dict[str, Any]]]:
    """Call one enrichment tool for all entities in parallel.

    Returns (formatted_text, structured_items) where structured_items carry
    the tool_id so they can be stored in context_enrichment_sources.
    """
    tool_name = tool_config.mcp_tool_name
    tool_id = getattr(tool_config, "tool_id", tool_name)
    canonical = {"entity_name": "", "limit": _CONTEXT_ENRICHMENT_RESULTS_PER_ENTITY}

    async def _query_one(entity: str) -> tuple[str, List[Dict[str, Any]]]:
        params = tool_config.map_parameters({**canonical, "entity_name": entity})
        raw = await _call_enrichment_tool_for_entity(tool_name, params, mcp_client)
        if raw is None:
            return "", []
        text, items = _parse_enrichment_result(raw)
        # tag each item with entity and tool_id for citation building
        for item in items:
            item.setdefault("tool_id", tool_id)
            item.setdefault("entity", entity)
        return text, items

    per_entity = await asyncio.gather(*[_query_one(e) for e in entities])

    text_lines: List[str] = []
    all_items: List[Dict[str, Any]] = []
    for entity, (text, items) in zip(entities, per_entity):
        if text:
            text_lines.append(f"[{entity}]\n{text}")
        all_items.extend(items)

    return "\n\n".join(text_lines), all_items


async def _phase2_6_fetch_context_enrichment(
    state: WorkflowState,
    config: SearchConfig,
    mcp_client: MCPToolClient,
) -> tuple[str, List[Dict[str, Any]]]:
    """Phase 2.6: fetch background context from configured knowledge-graph tools.

    Completely YAML-driven: only runs when the literature_review workflow
    lists tools under 'context_enrichment_tools'. Returns ("", []) when not
    configured, keeping lit review unchanged for other domains.

    Calls all configured tools × all extracted entities in parallel.
    Output text is capped to avoid bloating the synthesis prompt.

    Returns:
        (formatted_text_for_synthesis, structured_items_for_citation_index)
    """
    empty: tuple[str, List[Dict[str, Any]]] = ("", [])

    workflow = config.workflow
    if not workflow or not workflow.context_enrichment_tools:
        return empty

    tool_registry = config.tool_registry
    if not tool_registry:
        return empty

    entities = extract_entity_names(state["research_goal"], max_entities=3)
    if not entities:
        logger.debug("context enrichment: no entities extracted from research goal")
        return empty

    logger.info(
        f"Phase 2.6: fetching context enrichment for entities {entities} "
        f"via {len(workflow.context_enrichment_tools)} tool(s)"
    )

    tool_configs = []
    for tool_id in workflow.context_enrichment_tools:
        tc = tool_registry.get_tool(tool_id)
        if tc and tc.enabled and mcp_client.has_tool(tc.mcp_tool_name):
            # stash the yaml tool_id for downstream citation building
            tc._yaml_tool_id = tool_id
            tool_configs.append(tc)
        else:
            logger.debug(f"context enrichment: tool '{tool_id}' unavailable or disabled")

    if not tool_configs:
        return empty

    tool_tasks = [
        _call_enrichment_tool_for_entities(tc, entities, mcp_client)
        for tc in tool_configs
    ]
    tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

    sections: List[str] = []
    all_structured: List[Dict[str, Any]] = []
    for tc, result in zip(tool_configs, tool_results):
        if isinstance(result, Exception):
            logger.debug(f"context enrichment: {tc.mcp_tool_name} raised {result}")
            continue
        text, items = result
        if text:
            sections.append(f"**{tc.display_name}**\n{text}")
        # tag items with the yaml tool_id
        yaml_tool_id = getattr(tc, "_yaml_tool_id", tc.mcp_tool_name)
        for item in items:
            item["tool_id"] = yaml_tool_id
        all_structured.extend(items)

    if not sections and not all_structured:
        return empty

    combined = "\n\n".join(sections)
    if len(combined) > _CONTEXT_ENRICHMENT_MAX_CHARS:
        combined = combined[: _CONTEXT_ENRICHMENT_MAX_CHARS] + "\n[...truncated]"

    logger.info(
        f"Phase 2.6 complete: {len(sections)} tool(s), {len(all_structured)} structured items "
        f"({len(combined)} chars)"
    )
    return combined, all_structured


# =============================================================================
# KG evidence section formatting (appended to synthesis after articles are built)
# =============================================================================


def _format_kg_section_with_keys(
    context_enrichment_sources: List[Dict[str, Any]],
    paper_count: int,
) -> str:
    """Format context enrichment sources as a labeled [C*] section.

    Keys start at C{paper_count + 1}, exactly matching what build_reference_index
    will assign at generation time (papers fill C1..Cn first, then these entries
    follow). This lets the generation LLM see the same [C*] handles in
    articles_with_reasoning that appear in its Citation Reference List.
    """
    if not context_enrichment_sources:
        return ""
    lines = []
    for i, item in enumerate(context_enrichment_sources):
        key = f"C{paper_count + i + 1}"
        display = item.get("display", "External source")
        lines.append(f"[{key}] {display}")
    return "\n\n---\n\n## Knowledge Graph Evidence\n\n" + "\n\n".join(lines)


# =============================================================================
# Phase 3: Paper analysis
# =============================================================================


async def _analyze_single_paper(
    paper_id: str,
    metadata: Dict[str, Any],
    research_goal: str,
    model_name: str,
) -> Optional[Dict[str, Any]]:
    """Analyze a single paper for gaps and opportunities."""
    try:
        year = metadata.get("year")
        if not year and "date_revised" in metadata:
            try:
                year = int(metadata["date_revised"].split("/")[0])
            except (ValueError, KeyError, IndexError, AttributeError):
                pass

        content = get_paper_content_for_analysis(metadata)

        prompt = get_literature_review_paper_analysis_prompt(
            research_goal=research_goal,
            title=metadata.get("title", "Unknown"),
            authors=metadata.get("authors", []),
            year=year,
            fulltext=content,
        )

        analysis = await call_llm_json(
            prompt=prompt,
            model_name=model_name,
            json_schema=LITERATURE_PAPER_ANALYSIS_SCHEMA,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=HIGH_TEMPERATURE,
        )

        logger.debug(f"Analyzed paper {paper_id}: {metadata.get('title', 'Unknown')[:60]}")
        return {"paper_id": paper_id, "metadata": metadata, "analysis": analysis}

    except Exception as e:
        logger.error(f"Failed to analyze paper {paper_id}: {e}")
        return None


async def _phase3_analyze_papers(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    state: WorkflowState,
) -> List[Dict[str, Any]]:
    """Phase 3: Analyze papers with content for gaps and opportunities."""
    papers_with_content = get_papers_with_content(all_paper_metadata)

    if not papers_with_content:
        logger.error("No papers have content for analysis")
        return []

    logger.info(f"Phase 3: analyzing {len(papers_with_content)} papers (parallel)")

    tasks = [
        _analyze_single_paper(
            paper_id,
            metadata,
            state["research_goal"],
            state["model_name"],
        )
        for paper_id, metadata in papers_with_content.items()
    ]
    results = await asyncio.gather(*tasks)

    # filter out failed analyses
    analyses = [r for r in results if r is not None]
    logger.info(f"Completed {len(analyses)}/{len(papers_with_content)} paper analyses")

    # debug logging
    if analyses:
        first = analyses[0]
        logger.debug(f"Sample analysis structure - keys: {list(first.get('analysis', {}).keys())}")

    return analyses


# =============================================================================
# Phase 4: Synthesis
# =============================================================================


async def _phase4_synthesize(
    paper_analyses: List[Dict[str, Any]],
    state: WorkflowState,
    background_context: str = "",
) -> str:
    """Phase 4: Synthesize across papers to create articles_with_reasoning."""
    if not paper_analyses:
        logger.error("No paper analyses available for synthesis")
        return LITERATURE_REVIEW_FAILED

    logger.info("Phase 4: synthesizing across papers")

    try:
        prompt = get_literature_review_synthesis_prompt(
            research_goal=state["research_goal"],
            paper_analyses=paper_analyses,
            background_context=background_context,
        )

        save_prompt_to_disk(
            run_id=state.get("run_id", "unknown"),
            prompt_name="literature_review_synthesis",
            content=prompt,
            metadata={
                "prompt_length_chars": len(prompt),
                "papers_analyzed": len(paper_analyses),
            },
        )

        logger.info(f"Calling synthesis LLM with {len(prompt)} chars, {len(paper_analyses)} papers")

        synthesis = await call_llm(
            prompt=prompt,
            model_name=state["model_name"],
            max_tokens=EXTENDED_MAX_TOKENS,
            temperature=HIGH_TEMPERATURE,
        )

        logger.info(f"Synthesis complete - length: {len(synthesis)} chars")
        logger.debug(f"Synthesis preview: {synthesis[:500]}...")

        return synthesis

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return LITERATURE_REVIEW_FAILED


# =============================================================================
# Main node function
# =============================================================================


async def literature_review_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Conduct literature review using configured MCP tools with direct LLM analysis.

    Orchestrates the following phases:
    1. Generate search queries (MCP tool or LLM)
    2. Collect papers from configured sources
    3. Discover PDF links (for sources returning landing pages)
    4. Fetch content (for sources without fulltext)
    5. Analyze each paper for gaps/limitations
    6. Synthesize findings into articles_with_reasoning
    """
    logger.info("Starting literature review node")

    # setup configuration
    config = _get_search_config(state)
    logger.info(f"Literature review config: dev_mode={config.is_dev_mode}, papers={config.papers_to_read_count}")

    # check cache
    node_cache = get_node_cache()
    cache_params = {"research_goal": state["research_goal"]}
    force_cache = state.get("dev_test_lit_tools_isolation", False)

    if force_cache:
        logger.info("Dev isolation mode: forcing literature review cache")

    cached = node_cache.get("literature_review", force=force_cache, **cache_params)
    if cached is not None:
        logger.info("Literature review cache hit")
        await emit_progress(state, "literature_review_complete", "Literature review completed (cached)", 0.2, cached=True)
        return cached

    # check source availability
    source_available = await check_literature_source_available(tool_registry=config.tool_registry)
    if not source_available:
        logger.error("Literature source MCP service unavailable")
        await emit_progress(state, "literature_review_error", "Literature review failed (source unavailable)", 0.2)
        return make_failure_result("literature source service unavailable")

    await emit_progress(state, "literature_review_start", "Conducting literature review...", 0.1)

    # initialize MCP client
    mcp_client = await get_mcp_client(tool_registry=config.tool_registry)

    # phase 1: generate queries
    queries = await _phase1_generate_queries(state, config, mcp_client)

    # phase 2: collect papers
    slug = "research_" + hashlib.md5(state["research_goal"].encode()).hexdigest()[:8]

    if config.is_multi_source:
        all_paper_metadata, paper_source_map = await _phase2_collect_papers_multi_source(
            queries, slug, state, config, mcp_client
        )
    else:
        all_paper_metadata, paper_source_map = await _phase2_collect_papers_single_source(
            queries, slug, state, config, mcp_client
        )

    # phase 2.4: discover PDF links
    await _phase2_4_discover_pdf_links(all_paper_metadata, paper_source_map, config, mcp_client)

    # phase 2.5 + 2.6: fetch content and context enrichment in parallel
    content_task = _phase2_5_fetch_content(
        all_paper_metadata, paper_source_map, config, mcp_client, state
    )
    enrichment_task = _phase2_6_fetch_context_enrichment(state, config, mcp_client)
    _, enrichment_result = await asyncio.gather(content_task, enrichment_task)
    background_context, context_enrichment_sources = enrichment_result

    # check fulltext availability
    with_fulltext, without_fulltext = count_papers_with_fulltext(all_paper_metadata)
    logger.info(f"Collected {len(all_paper_metadata)} papers ({with_fulltext} with fulltext)")

    if without_fulltext > 0:
        logger.warning(f"{without_fulltext} papers do not have fulltexts available")

    # handle edge cases
    if len(all_paper_metadata) == 0:
        logger.warning("No papers collected")
        await emit_progress(state, "literature_review_complete", "Literature review completed (no papers found)", 0.2)
        return make_failure_result("no papers found", queries=queries)

    if with_fulltext == 0:
        logger.error("No papers have fulltexts available - cannot perform analysis")
        await emit_progress(
            state,
            "literature_review_complete",
            f"Literature review failed ({len(all_paper_metadata)} papers found but none have fulltexts)",
            0.2,
        )
        articles = build_articles_from_metadata(
            all_paper_metadata, paper_source_map, config.source_name, config.tool_registry
        )
        return make_failure_result(
            f"{len(all_paper_metadata)} papers found but none have fulltexts for analysis",
            queries=queries,
            articles=articles,
        )

    # log sample papers for debugging
    for paper_id, meta in list(all_paper_metadata.items())[:3]:
        has_ft = bool(meta.get("pmc_full_text_id") or meta.get("fulltext") or meta.get("pdf_url"))
        logger.debug(f"Paper {paper_id}: title='{meta.get('title', '')[:60]}...' has_fulltext={has_ft}")

    # phase 3: analyze papers
    paper_analyses = await _phase3_analyze_papers(all_paper_metadata, state)

    # phase 4: synthesize
    if paper_analyses:
        synthesis = await _phase4_synthesize(paper_analyses, state, background_context)
    else:
        synthesis = LITERATURE_REVIEW_FAILED

    # phase 5: create articles
    logger.info("Phase 5: creating article objects")
    articles = build_articles_from_metadata(
        all_paper_metadata, paper_source_map, config.source_name, config.tool_registry
    )
    logger.info(f"Created {len(articles)} article objects")

    # append knowledge graph evidence with [C*] keys aligned to the reference index.
    # keys start after the analyzed papers so they match what build_reference_index
    # will assign at generation time — giving the generation LLM explicit handles to cite.
    if context_enrichment_sources and synthesis != LITERATURE_REVIEW_FAILED:
        used_paper_count = sum(
            1 for a in articles if getattr(a, "used_in_analysis", False)
        )
        kg_section = _format_kg_section_with_keys(context_enrichment_sources, used_paper_count)
        if kg_section:
            synthesis = synthesis + kg_section
            logger.info(
                f"Appended {len(context_enrichment_sources)} KG source(s) with "
                f"[C{used_paper_count + 1}...] keys to synthesis"
            )

    # emit completion
    await emit_progress(
        state,
        "literature_review_complete",
        "Literature review completed",
        0.2,
        queries_count=len(queries),
        articles_count=len(articles),
    )

    logger.info(
        f"Literature review complete: {len(articles)} articles from {len(queries)} queries, "
        f"{len(synthesis)} char synthesis"
    )

    # build and cache result
    result = make_success_result(synthesis, queries, articles)
    if context_enrichment_sources:
        result["context_enrichment_sources"] = context_enrichment_sources
    node_cache.set("literature_review", result, force=force_cache, **cache_params)

    return result
