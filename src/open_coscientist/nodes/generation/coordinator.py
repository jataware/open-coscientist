"""
Generation coordinator - orchestrates all generation strategies.

All generation paths output hypotheses with explanation, literature_grounding, and experiment fields.
When no literature is available, literature_grounding contains an explicit warning message.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ...constants import (
    PROGRESS_GENERATE_START,
    PROGRESS_GENERATE_COMPLETE,
    LITERATURE_REVIEW_FAILED,
)
from ...models import Hypothesis
from ...state import WorkflowState
from .debate import generate_with_debate
from .literature_tools import generate_with_tools

logger = logging.getLogger(__name__)


@dataclass
class GenerationCounts:
    """Encapsulates hypothesis count allocation across generation methods"""

    tools_count: int
    debate_with_lit_count: int
    debate_only_count: int
    is_dev_isolation: bool = False
    is_degraded_mode: bool = False


@dataclass
class GenerationResults:
    """Encapsulates results from parallel generation execution"""

    tools_hypotheses: List[Hypothesis]
    debate_with_lit_hypotheses: List[Hypothesis]
    debate_only_hypotheses: List[Hypothesis]
    debate_transcripts: List[Dict[str, Any]]


# helper functions

def _check_literature_availability(
    articles_with_reasoning: Optional[str],
    mcp_available: bool
) -> bool:
    """Determine if literature review is available and valid"""
    return (
        articles_with_reasoning is not None
        and articles_with_reasoning != LITERATURE_REVIEW_FAILED
        and mcp_available
    )


def _determine_generation_counts(
    state: WorkflowState,
    total_count: int,
    has_literature: bool,
    enable_tool_calling: bool
) -> GenerationCounts:
    """Determine how many hypotheses to generate with each method"""
    if state.get("dev_test_lit_tools_isolation", False):
        return GenerationCounts(
            tools_count=total_count,
            debate_with_lit_count=0,
            debate_only_count=0,
            is_dev_isolation=True,
        )

    # condition (a)
    if has_literature and enable_tool_calling:
        # split 50/50, but ensure we don't exceed total_count
        tools_count = max(1, total_count // 2)
        debate_with_lit_count = total_count - tools_count
        # if total_count=1, tools_count=1, debate_with_lit_count=0
        # in this case, adjust to just use tools
        if debate_with_lit_count == 0:
            tools_count = total_count
        return GenerationCounts(
            tools_count=tools_count,
            debate_with_lit_count=debate_with_lit_count,
            debate_only_count=0,
        )

    # condition (c)
    if has_literature and not enable_tool_calling:
        return GenerationCounts(
            tools_count=0,
            debate_with_lit_count=total_count,
            debate_only_count=0,
        )

    # condition (b)
    return GenerationCounts(
        tools_count=0,
        debate_with_lit_count=0,
        debate_only_count=total_count,
        is_degraded_mode=True,
    )


def _log_generation_strategy(counts: GenerationCounts, total_count: int):
    """Log which generation strategy is being used"""
    if counts.is_dev_isolation:
        logger.info(
            "Dev isolation mode: allocating all hypotheses to lit tools generation (no debate)"
        )
        return

    if counts.tools_count > 0 and counts.debate_with_lit_count > 0:
        logger.info(
            f"Condition (a): Generating {total_count} hypotheses with literature review "
            f"({counts.tools_count} tool-based + {counts.debate_with_lit_count} debate-with-literature)"
        )
    elif counts.debate_with_lit_count > 0:
        logger.info(
            f"Condition (c): Generating {total_count} hypotheses with debate-with-literature"
        )
    elif counts.is_degraded_mode:
        logger.warning("=" * 80)
        logger.warning("No literature review tools available")
        logger.warning("Generating hypotheses from model latent knowledge only")
        logger.warning("=" * 80)


async def _emit_start_progress(state: WorkflowState, counts: GenerationCounts, total_count: int):
    """Emit progress callback for generation start"""
    progress_callback = state.get("progress_callback")
    if not progress_callback:
        return

    if counts.is_dev_isolation:
        await progress_callback(
            "generation_start",
            {
                "message": f"Generating {total_count} hypotheses with lit tools only (dev isolation mode)...",
                "progress": PROGRESS_GENERATE_START,
                "dev_isolation_mode": True,
            },
        )
    elif counts.tools_count > 0 and counts.debate_with_lit_count > 0:
        await progress_callback(
            "generation_start",
            {
                "message": f"Generating {total_count} hypotheses ({counts.tools_count} tool-based + {counts.debate_with_lit_count} debate-with-literature)...",
                "progress": PROGRESS_GENERATE_START,
            },
        )
    elif counts.debate_with_lit_count > 0:
        await progress_callback(
            "generation_start",
            {
                "message": f"Generating {total_count} hypotheses with debate-with-literature...",
                "progress": PROGRESS_GENERATE_START,
            },
        )
    elif counts.is_degraded_mode:
        await progress_callback(
            "generation_start",
            {
                "message": f"Generating {counts.debate_only_count} hypotheses without literature review...",
                "progress": PROGRESS_GENERATE_START,
                "literature_review_available": False,
                "degraded_mode": True,
            },
        )


async def _execute_generation_tasks(
    state: WorkflowState,
    counts: GenerationCounts,
    articles_with_reasoning: Optional[str]
) -> GenerationResults:
    """Execute parallel generation tasks and return results"""
    tools_hypotheses = []
    debate_with_lit_hypotheses = []
    debate_only_hypotheses = []
    debate_transcripts = []

    # collect tasks to run in parallel
    tasks = []

    if counts.tools_count > 0:
        logger.info(f"Running tool-based generation for {counts.tools_count} hypotheses")
        tasks.append(("tools", generate_with_tools(state, counts.tools_count)))

    if counts.debate_with_lit_count > 0:
        logger.info(f"Running debate-with-literature for {counts.debate_with_lit_count} hypotheses")
        tasks.append(
            (
                "debate_lit",
                generate_with_debate(
                    state=state,
                    count=counts.debate_with_lit_count,
                    articles_with_reasoning=articles_with_reasoning,
                ),
            )
        )

    if counts.debate_only_count > 0:
        logger.info(f"Running debate-only for {counts.debate_only_count} hypotheses")
        tasks.append(
            (
                "debate_only",
                generate_with_debate(
                    state=state,
                    count=counts.debate_only_count,
                    articles_with_reasoning=None,  # explicitly no literature
                ),
            )
        )

    # run all tasks in parallel
    results = await asyncio.gather(*[task for _, task in tasks])

    # unpack results
    for i, (task_type, _) in enumerate(tasks):
        if task_type == "tools":
            tools_hypotheses = results[i]
        elif task_type == "debate_lit":
            debate_with_lit_hypotheses, transcripts = results[i]
            debate_transcripts.extend(transcripts)
        elif task_type == "debate_only":
            debate_only_hypotheses, transcripts = results[i]
            debate_transcripts.extend(transcripts)

    return GenerationResults(
        tools_hypotheses=tools_hypotheses,
        debate_with_lit_hypotheses=debate_with_lit_hypotheses,
        debate_only_hypotheses=debate_only_hypotheses,
        debate_transcripts=debate_transcripts,
    )


def _apply_degraded_mode_fallback(hypotheses: List[Hypothesis]):
    """
    Set explicit literature_grounding message for hypotheses without literature review
    """
    for hyp in hypotheses:
        # always overwrite in non-lit-mcp mode to prevent hallucinated citations
        hyp.literature_grounding = (
            "No literature review available. This hypothesis is based on the model's "
            "latent knowledge and has not been validated against current research literature. "
            "Novelty and scientific validity should be independently verified."
        )


def _log_generation_summary(results: GenerationResults):
    """Log summary of generated hypotheses"""
    total = (
        len(results.tools_hypotheses)
        + len(results.debate_with_lit_hypotheses)
        + len(results.debate_only_hypotheses)
    )
    logger.info(
        f"Generated {total} total hypotheses "
        f"({len(results.tools_hypotheses)} tool-based, {len(results.debate_with_lit_hypotheses)} debate-with-lit, "
        f"{len(results.debate_only_hypotheses)} debate-only)"
    )

    if results.tools_hypotheses:
        logger.debug(
            f"tool-based generation_methods: {[h.generation_method for h in results.tools_hypotheses]}"
        )
    if results.debate_with_lit_hypotheses:
        logger.debug(
            f"debate-with-Lit generation_methods: {[h.generation_method for h in results.debate_with_lit_hypotheses]}"
        )
    if results.debate_only_hypotheses:
        logger.debug(
            f"debate-only generation_methods: {[h.generation_method for h in results.debate_only_hypotheses]}"
        )


def _build_summary_message_parts(results: GenerationResults, counts: GenerationCounts) -> List[str]:
    """Build message parts for summary output"""
    parts = []
    if counts.tools_count > 0:
        parts.append(f"{len(results.tools_hypotheses)} tool-based")
    if counts.debate_with_lit_count > 0:
        parts.append(f"{len(results.debate_with_lit_hypotheses)} debate-with-literature")
    if counts.debate_only_count > 0:
        suffix = ""
        parts.append(f"{len(results.debate_only_hypotheses)} debate-only{suffix}")
    return parts


async def _emit_complete_progress(
    state: WorkflowState,
    results: GenerationResults,
    counts: GenerationCounts
):
    """Emit progress callback for generation complete"""
    progress_callback = state.get("progress_callback")
    if not progress_callback:
        return

    parts = _build_summary_message_parts(results, counts)
    all_hypotheses = (
        results.tools_hypotheses
        + results.debate_with_lit_hypotheses
        + results.debate_only_hypotheses
    )

    message = f"Generated {len(all_hypotheses)} hypotheses ({', '.join(parts)})"

    await progress_callback(
        "generation_complete",
        {
            "message": message,
            "progress": PROGRESS_GENERATE_COMPLETE,
            "hypotheses_count": len(all_hypotheses),
        },
    )


# main coordinator function


async def generate_hypotheses(state: WorkflowState) -> Dict[str, Any]:
    """
    Coordinate hypothesis generation using appropriate strategies

    Implements 3-condition strategy:
    - Condition (a): lit review + tools → 50% tool-based + 50% debate-with-lit
    - Condition (b): no lit review → 100% debate-only
    - Condition (c): lit review but no tools → 100% debate-with-lit

    args:
        state: current workflow state

    returns:
        dict with hypotheses, debate_transcripts, metrics, and message
    """
    logger.info("Starting hypothesis generation")

    supervisor_guidance = state.get("supervisor_guidance")
    articles_with_reasoning = state.get("articles_with_reasoning")
    mcp_available = state.get("mcp_available", False)
    enable_tool_calling = state.get("enable_tool_calling_generation", False)
    total_count = state["initial_hypotheses_count"]

    if not supervisor_guidance:
        raise ValueError("No supervisor_guidance in state for node=generation")

    has_literature = _check_literature_availability(articles_with_reasoning, mcp_available)
    counts = _determine_generation_counts(state, total_count, has_literature, enable_tool_calling)

    _log_generation_strategy(counts, total_count)
    await _emit_start_progress(state, counts, total_count)

    try:
        results = await _execute_generation_tasks(state, counts, articles_with_reasoning)

        if counts.is_degraded_mode:
            _apply_degraded_mode_fallback(results.debate_only_hypotheses)

        _log_generation_summary(results)
        await _emit_complete_progress(state, results, counts)

        all_hypotheses = (
            results.tools_hypotheses
            + results.debate_with_lit_hypotheses
            + results.debate_only_hypotheses
        )

        parts = _build_summary_message_parts(results, counts)
        message_content = f"Generated {len(all_hypotheses)} hypotheses ({', '.join(parts)})"

        return {
            "hypotheses": all_hypotheses,
            "debate_transcripts": results.debate_transcripts,
            "hypothesis_count": len(all_hypotheses),
            "message": message_content,
        }

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise
