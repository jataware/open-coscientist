"""
Literature review helper functions.

Small, composable functions for the literature review node phases:
- Query generation
- Paper search and collection
- PDF discovery and content fetching
- Paper analysis
- Result building
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..constants import LITERATURE_REVIEW_FAILED
from ..models import Article

if TYPE_CHECKING:
    from ..config import ToolConfig, SearchSourceConfig, WorkflowConfig, ToolRegistry
    from ..mcp_client import MCPToolClient
    from ..state import WorkflowState

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration helpers
# =============================================================================


@dataclass
class SearchConfig:
    """Configuration for literature review search."""

    tool_registry: Optional["ToolRegistry"]
    workflow: Optional["WorkflowConfig"]
    is_multi_source: bool
    search_tool_name: str
    search_tool_config: Optional["ToolConfig"]
    source_name: str
    papers_to_read_count: int
    is_dev_mode: bool


def extract_source_name(tool_config: Optional["ToolConfig"]) -> str:
    """Extract source name from tool config's response_format field_mapping."""
    if not tool_config:
        return "unknown"
    if tool_config.response_format and tool_config.response_format.field_mapping:
        source_val = tool_config.response_format.field_mapping.get("source", "")
        if source_val.startswith("'") and source_val.endswith("'"):
            return source_val[1:-1]
    return tool_config.source_type or "unknown"


# =============================================================================
# Response normalization
# =============================================================================


def normalize_search_response(
    result_data: Any,
    tool_config: Optional["ToolConfig"],
) -> Dict[str, Dict[str, Any]]:
    """
    Normalize search tool response to standard {paper_id: metadata} format.

    Handles both dict responses (PubMed-style) and list responses (arXiv-style).
    """
    if not isinstance(result_data, (dict, list)):
        return {}

    if not tool_config or not tool_config.response_format:
        return result_data if isinstance(result_data, dict) else {}

    results_path = tool_config.response_format.results_path
    is_dict = tool_config.response_format.is_dict

    # extract results from nested path
    if results_path and results_path != ".":
        if isinstance(result_data, dict):
            result_data = result_data.get(results_path, result_data)

    if is_dict and isinstance(result_data, dict):
        return result_data

    if isinstance(result_data, list):
        source_id_field = tool_config.response_format.field_mapping.get("source_id", "source_id")
        if source_id_field.startswith("@"):
            source_id_field = "arxiv_id"

        normalized = {}
        for paper in result_data:
            paper_id = (
                paper.get(source_id_field)
                or paper.get("arxiv_id")
                or paper.get("id")
                or str(len(normalized))
            )
            normalized[paper_id] = paper
        return normalized

    return result_data if isinstance(result_data, dict) else {}


# =============================================================================
# Article building
# =============================================================================


def build_article_from_metadata(
    paper_id: str,
    metadata: Dict[str, Any],
    source_name: str = "pubmed",
    used_in_analysis: bool = True,
) -> Article:
    """Build an Article object from MCP response metadata."""
    year = _parse_year_from_metadata(metadata)
    url = _build_article_url(paper_id, metadata, source_name)

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


def _parse_year_from_metadata(metadata: Dict[str, Any]) -> Optional[int]:
    """Parse year from metadata, handling multiple formats."""
    if "year" in metadata and metadata["year"]:
        try:
            return int(metadata["year"])
        except (ValueError, TypeError):
            pass

    if "date_revised" in metadata:
        try:
            year_str = metadata["date_revised"].split("/")[0]
            return int(year_str)
        except (ValueError, KeyError, IndexError, AttributeError):
            pass

    return None


def _build_article_url(paper_id: str, metadata: Dict[str, Any], source_name: str) -> str:
    """Build URL for article, using metadata URL or constructing default."""
    url = metadata.get("url")
    if url:
        return url

    if source_name == "pubmed":
        return f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"

    if paper_id.startswith("10."):
        return f"https://doi.org/{paper_id}"

    return paper_id


def build_articles_from_metadata(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    paper_source_map: Dict[str, str],
    default_source_name: str,
    tool_registry: Optional["ToolRegistry"] = None,
) -> List[Article]:
    """Build Article objects from collected paper metadata."""
    articles = []
    for paper_id, metadata in all_paper_metadata.items():
        if isinstance(metadata, dict):
            paper_source = metadata.get("_source_name", default_source_name)
        else:
            paper_source = default_source_name

        articles.append(
            build_article_from_metadata(paper_id, metadata, paper_source, used_in_analysis=True)
        )
    return articles


# =============================================================================
# Fulltext availability
# =============================================================================


def count_papers_with_fulltext(all_paper_metadata: Dict[str, Dict[str, Any]]) -> Tuple[int, int]:
    """
    Count papers with and without fulltext indicators.

    Returns:
        Tuple of (papers_with_fulltext, papers_without_fulltext)
    """
    with_fulltext = 0
    for pid, meta in all_paper_metadata.items():
        if not isinstance(meta, dict):
            continue
        if (
            meta.get("pmc_full_text_id")
            or meta.get("fulltext")
            or meta.get("has_fulltext")
            or meta.get("pdf_url")
        ):
            with_fulltext += 1

    without_fulltext = len(all_paper_metadata) - with_fulltext
    return with_fulltext, without_fulltext


def get_papers_with_content(
    all_paper_metadata: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Get papers that have content available for analysis.

    Papers with fulltext are preferred. Papers with pdf_url and abstract
    can use abstract as fallback.
    """
    papers_with_content = {}
    for pid, metadata in all_paper_metadata.items():
        if not isinstance(metadata, dict):
            continue
        if metadata.get("fulltext"):
            papers_with_content[pid] = metadata
        elif metadata.get("pdf_url") and metadata.get("abstract"):
            papers_with_content[pid] = metadata
            logger.debug(f"Paper {pid}: using abstract for analysis (fulltext not downloaded)")
    return papers_with_content


# =============================================================================
# Result builders
# =============================================================================


def make_failure_result(
    reason: str,
    queries: List[str] = None,
    articles: List[Article] = None,
) -> Dict[str, Any]:
    """Create a failure result dict for early returns."""
    return {
        "articles_with_reasoning": LITERATURE_REVIEW_FAILED,
        "literature_review_queries": queries or [],
        "articles": articles or [],
        "messages": [
            {
                "role": "assistant",
                "content": f"literature review failed - {reason}",
                "metadata": {"phase": "literature_review", "error": True},
            }
        ],
    }


def make_success_result(
    synthesis: str,
    queries: List[str],
    articles: List[Article],
) -> Dict[str, Any]:
    """Create a success result dict."""
    return {
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


# =============================================================================
# Progress helpers
# =============================================================================


async def emit_progress(
    state: "WorkflowState",
    event: str,
    message: str,
    progress: float,
    **extra,
) -> None:
    """Emit progress callback if configured."""
    callback = state.get("progress_callback")
    if callback:
        await callback(event, {"message": message, "progress": progress, **extra})


# =============================================================================
# Query generation helpers
# =============================================================================


def parse_mcp_query_result(result: Any) -> List[str]:
    """Parse MCP tool result into list of queries."""
    if isinstance(result, str):
        try:
            result_data = json.loads(result)
            if isinstance(result_data, list):
                return result_data
            return result_data.get("queries", [])
        except json.JSONDecodeError:
            return []
    elif isinstance(result, list):
        return result
    return []


def determine_query_source_type(
    workflow: Optional["WorkflowConfig"],
    tool_registry: Optional["ToolRegistry"],
    search_tool_config: Optional["ToolConfig"],
    is_multi_source: bool,
) -> str:
    """Determine the source type for query generation prompt selection."""
    if is_multi_source and workflow and tool_registry:
        source_types = []
        for source in workflow.get_enabled_search_sources():
            tool_cfg = tool_registry.get_tool(source.tool)
            if tool_cfg:
                source_types.append(tool_cfg.source_type)

        if "knowledge_graph" in source_types and len(source_types) > 1:
            logger.warning(
                "Multi-source mode with knowledge_graph detected. "
                "Using generic queries. For best results, use per-source query generation."
            )
            return "academic"
        elif "knowledge_graph" in source_types:
            return "knowledge_graph"
        return "academic"

    if search_tool_config:
        return search_tool_config.source_type or "academic"

    return "academic"


# =============================================================================
# Search helpers
# =============================================================================


def calculate_papers_per_query(
    total_papers: int,
    num_queries: int,
) -> Tuple[int, int]:
    """
    Calculate papers per query with remainder distribution.

    Returns:
        Tuple of (papers_per_query, remainder)
    """
    papers_per_query = total_papers // num_queries
    remainder = total_papers % num_queries

    if papers_per_query < 2:
        papers_per_query = 2
        logger.warning(
            f"Target {total_papers} papers with {num_queries} queries gives <2 per query, using 2 minimum"
        )

    return papers_per_query, remainder


def merge_search_results(
    source_results: List[Tuple[str, Dict[str, Dict[str, Any]]]],
    deduplicate: bool = True,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Merge results from multiple sources.

    Args:
        source_results: List of (source_tool_id, results_dict) tuples
        deduplicate: Whether to deduplicate by title

    Returns:
        Tuple of (merged_metadata, paper_source_map)
    """
    all_paper_metadata: Dict[str, Dict[str, Any]] = {}
    paper_source_map: Dict[str, str] = {}
    seen_titles: set = set()

    for source_tool_id, results in source_results:
        for paper_id, metadata in results.items():
            if deduplicate and isinstance(metadata, dict):
                title = (metadata.get("title") or "").lower().strip()
                if title and title in seen_titles:
                    logger.debug(f"Skipping duplicate: {title[:60]}...")
                    continue
                if title:
                    seen_titles.add(title)

            all_paper_metadata[paper_id] = metadata
            paper_source_map[paper_id] = source_tool_id

    return all_paper_metadata, paper_source_map


# =============================================================================
# PDF discovery helpers
# =============================================================================


def build_pdf_discovery_config(
    workflow: Optional["WorkflowConfig"],
    tool_registry: Optional["ToolRegistry"],
    is_multi_source: bool,
) -> Dict[str, Tuple[str, str]]:
    """
    Build PDF discovery configuration mapping.

    Returns:
        Dict mapping source_tool_id -> (mcp_tool_name, url_field)
    """
    config: Dict[str, Tuple[str, str]] = {}

    if is_multi_source and workflow and tool_registry:
        for source in workflow.get_enabled_search_sources():
            discovery_tool = source.pdf_discovery_tool or (
                workflow.pdf_discovery_tool if workflow else None
            )
            discovery_url_field = source.pdf_discovery_url_field or (
                workflow.pdf_discovery_url_field if workflow else "url"
            )
            if discovery_tool:
                tool_cfg = tool_registry.get_tool(discovery_tool)
                if tool_cfg:
                    config[source.tool] = (tool_cfg.mcp_tool_name, discovery_url_field)

    elif tool_registry and workflow and workflow.pdf_discovery_tool:
        tool_cfg = tool_registry.get_tool(workflow.pdf_discovery_tool)
        if tool_cfg:
            config["_default"] = (tool_cfg.mcp_tool_name, workflow.pdf_discovery_url_field)

    return config


def get_papers_needing_pdf_discovery(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    paper_source_map: Dict[str, str],
    pdf_discovery_config: Dict[str, Tuple[str, str]],
) -> List[Tuple[str, Dict, str, str]]:
    """
    Identify papers that need PDF discovery.

    Returns:
        List of (paper_id, metadata, tool_name, url_field) tuples
    """
    papers = []
    for pid, meta in all_paper_metadata.items():
        if not isinstance(meta, dict) or meta.get("pdf_url"):
            continue

        source_tool_id = paper_source_map.get(pid, "_default")
        config = pdf_discovery_config.get(source_tool_id) or pdf_discovery_config.get("_default")
        if not config:
            continue

        tool_name, url_field = config
        landing_url = meta.get(url_field)
        if landing_url:
            papers.append((pid, meta, tool_name, url_field))

    return papers


def parse_pdf_discovery_result(result: Any) -> Optional[str]:
    """Parse PDF discovery result to extract PDF URL."""
    if isinstance(result, str):
        try:
            result_data = json.loads(result)
            if isinstance(result_data, list) and result_data:
                return result_data[0]
            if isinstance(result_data, dict):
                links = result_data.get("pdf_links") or result_data.get("links") or []
                if links:
                    first_link = links[0]
                    return first_link if isinstance(first_link, str) else first_link.get("url")
        except json.JSONDecodeError:
            if result.startswith("http"):
                return result
    elif isinstance(result, list) and result:
        first = result[0]
        return first if isinstance(first, str) else first.get("url")
    return None


# =============================================================================
# Content fetching helpers
# =============================================================================


def build_content_config(
    workflow: Optional["WorkflowConfig"],
    tool_registry: Optional["ToolRegistry"],
    is_multi_source: bool,
) -> Dict[str, Tuple[str, str]]:
    """
    Build content retrieval configuration mapping.

    Returns:
        Dict mapping source_tool_id -> (mcp_tool_name, url_field)
    """
    config: Dict[str, Tuple[str, str]] = {}

    if is_multi_source and workflow and tool_registry:
        workflow_content_tool = workflow.content_tool
        workflow_url_field = workflow.content_url_field

        for source in workflow.get_enabled_search_sources():
            src_content_tool = source.content_tool or workflow_content_tool
            src_url_field = source.content_url_field or workflow_url_field

            if src_content_tool:
                tool_cfg = tool_registry.get_tool(src_content_tool)
                if tool_cfg:
                    config[source.tool] = (tool_cfg.mcp_tool_name, src_url_field)

    elif tool_registry and workflow and workflow.content_tool:
        content_tool_cfg = tool_registry.get_tool(workflow.content_tool)
        if content_tool_cfg:
            config["_default"] = (content_tool_cfg.mcp_tool_name, workflow.content_url_field)

    return config


def get_papers_needing_content(
    all_paper_metadata: Dict[str, Dict[str, Any]],
    paper_source_map: Dict[str, str],
    content_config: Dict[str, Tuple[str, str]],
) -> List[Tuple[str, Dict, str, str]]:
    """
    Identify papers that need content retrieval.

    Returns:
        List of (paper_id, metadata, tool_name, url_field) tuples
    """
    papers = []
    for pid, meta in all_paper_metadata.items():
        if not isinstance(meta, dict) or meta.get("fulltext"):
            continue

        source_tool_id = paper_source_map.get(pid, "_default")
        config = content_config.get(source_tool_id) or content_config.get("_default")
        if not config:
            continue

        tool_name, url_field = config
        content_url = meta.get(url_field)
        if content_url:
            papers.append((pid, meta, tool_name, url_field))

    return papers


def parse_content_result(result: Any) -> Optional[str]:
    """Parse content fetch result to extract text content."""
    if isinstance(result, str):
        try:
            result_data = json.loads(result)
            return result_data.get("content") or result_data.get("text") or result
        except json.JSONDecodeError:
            return result
    elif isinstance(result, dict):
        return result.get("content") or result.get("text") or str(result)
    return str(result) if result else None


# =============================================================================
# Paper analysis helpers
# =============================================================================


def get_paper_content_for_analysis(metadata: Dict[str, Any], max_chars: int = 200_000) -> str:
    """Get paper content for analysis, with truncation if needed."""
    content = metadata.get("fulltext") or metadata.get("abstract") or ""
    if len(content) > max_chars:
        logger.debug(f"Truncating paper content to {max_chars} chars")
        content = content[:max_chars] + "\n\n[... truncated for length ...]"
    return content
