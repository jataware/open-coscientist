"""
Generation coordinator - orchestrates all generation strategies.

Decision tree:
1. Has literature review?
   - YES → literature_strategy + debate_strategy (parallel)
   - NO → standard_strategy + debate_strategy (parallel)

2. Which literature strategy?
   - enable_tool_calling_generation=True + MCP → tool-based (two-phase)
   - Otherwise → standard (pre-done review)
   - Fallback: tool-based failure → standard
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ...constants import (
    PROGRESS_GENERATE_START,
    PROGRESS_GENERATE_COMPLETE,
    LITERATURE_REVIEW_FAILED,
)
from ...models import Hypothesis
from ...state import WorkflowState
from .debate import generate_with_debate
from .literature_standard import generate_with_literature
from .literature_tools import generate_with_tools
from .standard import generate_standard

logger = logging.getLogger(__name__)


async def _literature_generation_strategy(
    state: WorkflowState,
    count: int,
    supervisor_guidance: Dict[str, Any],
    articles_with_reasoning: Optional[str],
    preferences: Optional[str],
    attributes: Optional[List[str]],
    user_hypotheses: Optional[List[str]],
    mcp_available: bool,
) -> List[Hypothesis]:
    """
    Decide which literature generation strategy to use.

    Tries tool-based first if enabled, falls back to standard

    returns:
        list of hypotheses from chosen literature strategy
    """
    if count == 0:
        return []

    # check if tool-based generation is enabled
    if state.get("enable_tool_calling_generation", False) and mcp_available:
        try:
            logger.info("Using tool-based literature generation (two-phase)")
            return await generate_with_tools(state, count)
        except Exception as e:
            logger.warning(f"Tool-based generation failed, falling back to standard: {e}")
            # fall through to standard generation

    # standard literature generation (with pre-processed literature review)
    logger.info("Using standard literature generation (pre-processed review)")
    return await generate_with_literature(
        state=state,
        count=count,
        supervisor_guidance=supervisor_guidance,
        articles_with_reasoning=articles_with_reasoning or "",
        preferences=preferences,
        attributes=attributes,
        user_hypotheses=user_hypotheses,
    )


async def generate_hypotheses(state: WorkflowState) -> Dict[str, Any]:
    """
    Coordinate hypothesis generation using appropriate strategies

    Decision tree:
    1. Has literature review + mcp available?
       - yes → literature + debate (parallel)
       - no → standard + debate (parallel)

    2. Which literature strategy?
       - enable_tool_calling_generation=true + mcp → tool-based (two-phase)
       - otherwise → standard (pre-processed review)

    args:
        state: current workflow state

    returns:
        dict with hypotheses, debate_transcripts, metrics, and message
    """
    logger.info("Starting hypothesis generation")

    # get common state variables
    supervisor_guidance = state.get("supervisor_guidance")
    articles_with_reasoning = state.get("articles_with_reasoning")
    preferences = state.get("preferences")
    attributes = state.get("attributes")
    user_hypotheses = state.get("user_inputs", {}).get("starting_hypotheses")
    mcp_available = state.get("mcp_available", False)

    # validate required state
    if not supervisor_guidance:
        raise ValueError("no supervisor_guidance in state for node=generation")

    # determine generation strategy based on literature review availability
    total_count = state["initial_hypotheses_count"]

    # dev isolation mode: allocate all to lit tools (no debate)
    if state.get("dev_test_lit_tools_isolation", False):
        logger.info(
            "Dev isolation mode: allocating all hypotheses to lit tools generation (no debate)"
        )
        lit_count = total_count
        debate_count = 0
        regular_count = 0

        # emit progress
        if state.get("progress_callback"):
            await state["progress_callback"](
                "generation_start",
                {
                    "message": f"generating {total_count} hypotheses with lit tools only (dev isolation mode)...",
                    "progress": PROGRESS_GENERATE_START,
                    "dev_isolation_mode": True,
                },
            )

    elif (
        articles_with_reasoning
        and articles_with_reasoning != LITERATURE_REVIEW_FAILED
        and mcp_available
    ):
        # mode 1: literature review available - use literature + debate
        lit_count = max(1, (total_count + 1) // 2)  # literature gets extra if odd
        debate_count = max(1, total_count // 2)
        regular_count = 0

        logger.info(
            f"Generating {total_count} hypotheses with literature review ({lit_count} literature + {debate_count} debate)"
        )

        # emit progress
        if state.get("progress_callback"):
            await state["progress_callback"](
                "generation_start",
                {
                    "message": f"Generating {total_count} hypotheses ({lit_count} literature + {debate_count} debate)...",
                    "progress": PROGRESS_GENERATE_START,
                },
            )
    else:
        # mode 2: no literature review - use debate + standard generation
        lit_count = 0
        debate_count = max(1, total_count // 2)
        regular_count = max(1, total_count - debate_count)

        logger.info("Literature review unavailable, proceeding without literature context")
        logger.info(
            f"Generating {total_count} hypotheses without literature review ({debate_count} debate + {regular_count} standard)"
        )

        # emit progress
        if state.get("progress_callback"):
            await state["progress_callback"](
                "generation_start",
                {
                    "message": f"Generating {total_count} hypotheses without literature review ({debate_count} debate + {regular_count} standard)...",
                    "progress": PROGRESS_GENERATE_START,
                    "literature_review_available": False,
                },
            )

    # run generation strategies in parallel
    try:
        if lit_count > 0:
            # mode 1: with literature review
            lit_hypotheses, debate_result = await asyncio.gather(
                _literature_generation_strategy(
                    state=state,
                    count=lit_count,
                    supervisor_guidance=supervisor_guidance,
                    articles_with_reasoning=articles_with_reasoning,
                    preferences=preferences,
                    attributes=attributes,
                    user_hypotheses=user_hypotheses,
                    mcp_available=mcp_available,
                ),
                generate_with_debate(state=state, count=debate_count),
            )

            # unpack debate results
            debate_hypotheses, debate_transcripts = debate_result
            regular_hypotheses = []

            # merge results
            all_hypotheses = lit_hypotheses + debate_hypotheses
            logger.info(
                f"Generated {len(all_hypotheses)} total hypotheses ({len(lit_hypotheses)} from literature, {len(debate_hypotheses)} from debate)"
            )

            # debug: log actual generation_method values
            lit_methods = [h.generation_method for h in lit_hypotheses]
            debate_methods = [h.generation_method for h in debate_hypotheses]
            logger.debug(f"literature hypotheses generation_methods: {lit_methods}")
            logger.debug(f"debate hypotheses generation_methods: {debate_methods}")

            # emit progress
            if state.get("progress_callback"):
                await state["progress_callback"](
                    "generation_complete",
                    {
                        "message": f"Generated {len(all_hypotheses)} hypotheses ({len(lit_hypotheses)} literature + {len(debate_hypotheses)} debate)",
                        "progress": PROGRESS_GENERATE_COMPLETE,
                        "hypotheses_count": len(all_hypotheses),
                    },
                )
        else:
            # mode 2: without literature review
            regular_hypotheses, debate_result = await asyncio.gather(
                generate_standard(
                    state=state,
                    count=regular_count,
                    supervisor_guidance=supervisor_guidance,
                    preferences=preferences,
                    attributes=attributes,
                    user_hypotheses=user_hypotheses,
                ),
                generate_with_debate(state=state, count=debate_count),
            )

            # unpack debate results
            debate_hypotheses, debate_transcripts = debate_result
            lit_hypotheses = []

            # merge results
            all_hypotheses = regular_hypotheses + debate_hypotheses
            logger.info(
                f"Generated {len(all_hypotheses)} total hypotheses ({len(regular_hypotheses)} standard, {len(debate_hypotheses)} from debate)"
            )

            # emit progress
            if state.get("progress_callback"):
                await state["progress_callback"](
                    "generation_complete",
                    {
                        "message": f"Generated {len(all_hypotheses)} hypotheses ({len(regular_hypotheses)} standard + {len(debate_hypotheses)} debate)",
                        "progress": PROGRESS_GENERATE_COMPLETE,
                        "hypotheses_count": len(all_hypotheses),
                        "literature_review_available": False,
                    },
                )

        # create message based on generation mode
        if lit_count > 0:
            message_content = f"Generated {len(all_hypotheses)} hypotheses ({len(lit_hypotheses)} literature + {len(debate_hypotheses)} debate)"
        else:
            message_content = f"Generated {len(all_hypotheses)} hypotheses ({len(regular_hypotheses)} standard + {len(debate_hypotheses)} debate, no literature review)"

        return {
            "hypotheses": all_hypotheses,
            "debate_transcripts": debate_transcripts,
            "hypothesis_count": len(all_hypotheses),
            "message": message_content,
        }

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise
