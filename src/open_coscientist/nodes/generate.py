"""
Generation node - creates initial hypotheses.

Main entry point for the LangGraph workflow. All generation logic
has been moved to the generation/ package for better organization.
"""

import logging
from typing import Any, Dict

from ..models import create_metrics_update
from ..state import WorkflowState
from .generation import generate_hypotheses

logger = logging.getLogger(__name__)


async def generate_node(state: WorkflowState) -> Dict[str, Any]:
    """
    LangGraph node for hypothesis generation

    Delegates to generation coordinator which orchestrates all strategies:
    - Literature usage (standard or tool-based)
    - Debate generation (with or without literature review, depending on configuration and availability)

    args:
        state: current workflow state

    returns:
        dict with hypotheses, debate_transcripts, metrics, and message
    """
    logger.info("Starting generate node")

    # delegate to coordinator
    result = await generate_hypotheses(state)

    # add metrics
    hypothesis_count = result.get("hypothesis_count", len(result.get("hypotheses", [])))
    metrics = create_metrics_update(hypothesis_count=hypothesis_count)
    result["metrics"] = metrics

    logger.info(f"Generate node complete: {result.get('message', 'generated hypotheses')}")

    return result
