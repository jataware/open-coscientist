"""
LangGraph state definition for hypothesis generation workflow.

The state is passed through all nodes and tracks the complete workflow.
"""

import logging
from typing import Annotated, Any, Callable, Dict, List, Optional

from langgraph.graph import add_messages
from typing_extensions import TypedDict

from .models import Article, ExecutionMetrics, Hypothesis

logger = logging.getLogger(__name__)


def deduplicate_hypotheses(existing: List[Hypothesis], new: List[Hypothesis]) -> List[Hypothesis]:
    """
    State reducer that automatically deduplicates hypotheses on state update.

    This is a LangGraph anti-duplicate strategy: duplicates are automatically
    removed every time the state is updated, preventing them from propagating.

    Args:
        existing: Existing hypotheses in state
        new: New hypotheses being added or replacing existing

    Returns:
        Deduplicated list of hypotheses
    """
    # If new list is provided, use it (this is a replacement operation)
    # Only merge if new contains different hypotheses
    if not new:
        return existing

    # Check if this is a replacement (same count or updating existing hypotheses)
    # vs. adding new hypotheses
    if len(new) > 0:
        # If first hypothesis in new has same id characteristics as existing,
        # this is a replacement operation, not addition
        existing_texts = {hyp.text.strip().lower() for hyp in existing}
        new_texts = {hyp.text.strip().lower() for hyp in new}

        # If substantial overlap, this is a replacement (e.g., updating metadata)
        overlap = existing_texts & new_texts
        if len(overlap) > len(new) * 0.5:  # More than 50% overlap
            # Replacement operation - use new list as-is but deduplicate within it
            all_hyps = new
        else:
            # Addition operation - merge and deduplicate
            all_hyps = existing + new
    else:
        all_hyps = existing + new

    # Deduplicate
    seen = set()
    deduplicated = []

    for hyp in all_hyps:
        # Use text hash for exact duplicate detection
        text_key = hyp.text.strip().lower()
        if text_key not in seen:
            seen.add(text_key)
            deduplicated.append(hyp)
        else:
            # Only log if this is truly a duplicate (not from replacement)
            if len(all_hyps) > len(new):
                logger.warning(f"Automatic dedup: Removed duplicate hypothesis: {hyp.text[:80]}...")

    return deduplicated


def merge_metrics(existing: ExecutionMetrics, new: ExecutionMetrics) -> ExecutionMetrics:
    """
    State reducer that merges metrics from multiple nodes.

    When multiple nodes update metrics concurrently, this combines them.

    Args:
        existing: Existing metrics in state
        new: New metrics being added (should contain only deltas)

    Returns:
        Merged metrics (new object, does not mutate inputs)
    """
    # Create a NEW metrics object (don't mutate existing!)
    merged_phase_times = {}

    # Merge phase times from both existing and new
    for phase, time_val in existing.phase_times.items():
        merged_phase_times[phase] = time_val

    for phase, time_val in new.phase_times.items():
        if phase in merged_phase_times:
            merged_phase_times[phase] += time_val
        else:
            merged_phase_times[phase] = time_val

    merged = ExecutionMetrics(
        hypothesis_count=max(existing.hypothesis_count, new.hypothesis_count),
        reviews_count=existing.reviews_count + new.reviews_count,
        tournaments_count=existing.tournaments_count + new.tournaments_count,
        evolutions_count=existing.evolutions_count + new.evolutions_count,
        llm_calls=existing.llm_calls + new.llm_calls,
        total_time=new.total_time if new.total_time > 0 else existing.total_time,
        phase_times=merged_phase_times,
    )

    return merged


class WorkflowState(TypedDict):
    """
    Complete state for the hypothesis generation workflow.

    This state is passed through all nodes in the LangGraph workflow.
    Each node reads from and writes to this state.
    """

    # Input
    research_goal: str
    """The research question to generate hypotheses for."""

    # Configuration
    model_name: str
    """LLM model to use (litellm format)."""

    max_iterations: int
    """Number of refinement iterations to run."""

    initial_hypotheses_count: int
    """Number of initial hypotheses to generate."""

    evolution_max_count: int
    """Number of top hypotheses to evolve each iteration."""

    # Workflow State
    hypotheses: Annotated[List[Hypothesis], deduplicate_hypotheses]
    """Current list of hypotheses being processed (auto-deduplicated)."""

    current_iteration: int
    """Current iteration number (0-indexed)."""

    supervisor_guidance: Dict[str, Any]
    """Supervisor's research plan and workflow guidance."""

    meta_review: Dict[str, Any]
    """Meta-review insights for guiding evolution."""

    removed_duplicates: List[Dict[str, Any]]
    """Tracking removed duplicate hypotheses."""

    tournament_matchups: List[Dict[str, Any]]
    """List of tournament matchups with reasoning."""

    evolution_details: List[Dict[str, Any]]
    """List of evolution transformations with reasoning."""

    # Metrics
    metrics: Annotated[ExecutionMetrics, merge_metrics]
    """Execution metrics for the workflow (auto-merged from concurrent updates)."""

    start_time: float
    """Workflow start timestamp."""

    run_id: str
    """Unique identifier for this run (used for logging)."""

    # Progress Callback
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]]
    """Optional callback for progress updates."""

    # Messages (for LangSmith tracing)
    messages: Annotated[List[Dict[str, Any]], add_messages]
    """Message history for LangSmith observability."""

    # Optional User Preferences and Inputs
    preferences: Optional[str]
    """Optional: Desired approach or focus for hypothesis generation."""

    attributes: Optional[List[str]]
    """Optional: Key qualities to prioritize in hypotheses."""

    constraints: Optional[List[str]]
    """Optional: Requirements or boundaries for hypothesis generation."""

    starting_hypotheses: Optional[List[str]]
    """Optional: User-provided starting hypotheses to build upon."""

    literature: Optional[List[str]]
    """Optional: User-provided literature references to incorporate."""

    articles_with_reasoning: Optional[str]
    """Literature review results with analytical reasoning (formatted for prompts)."""

    literature_review_queries: Optional[List[str]]
    """Generated search queries for literature review."""

    articles: Optional[List[Article]]
    """Individual articles extracted from literature review (for hypothesis comparison)."""

    generation_corpus_slug: Optional[str]
    """Shared corpus slug for reuse across draft and validation phases."""

    debate_transcripts: Optional[List[Dict[str, Any]]]
    """Internal debate transcripts from parallel debates. Each entry: {debate_id, transcript, hypothesis_text}"""

    mcp_available: Optional[bool]
    """Whether MCP server (for literature review tools) is available."""

    pubmed_available: Optional[bool]
    """Whether PubMed API (Entrez) is available."""

    enable_tool_calling_generation: Optional[bool]
    """Enable tool-calling generation where generate node queries literature tools directly (requires enable_literature_review_node=True + MCP server, default False)."""

    dev_test_lit_tools_isolation: Optional[bool]
    """Development mode: force cache on lit review, allocate all hypotheses to lit tools (no debate)."""


class WorkflowConfig(TypedDict):
    """Configuration for the hypothesis generation workflow."""

    model_name: str
    max_iterations: int
    initial_hypotheses_count: int
    evolution_max_count: int
