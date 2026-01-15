"""
Supervisor node - create research plan and workflow guidance.
"""

import logging
from typing import Any, Dict

from ..constants import (
    EXTENDED_MAX_TOKENS,
    MEDIUM_TEMPERATURE,
    PROGRESS_SUPERVISOR_START,
    PROGRESS_SUPERVISOR_COMPLETE,
)
from ..llm import call_llm_json
from ..models import create_metrics_update
from ..prompts import get_supervisor_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def supervisor_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Create research plan and provide workflow guidance.

    This node analyzes the research goal and configures an appropriate
    research plan, setting parameters and providing guidance for the
    entire workflow.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields (supervisor_guidance)
    """
    research_goal = state["research_goal"]
    logger.info(f"Supervisor analyzing research goal: {research_goal[:100]}...")

    # extract optional user inputs from state
    preferences = state.get("preferences")
    attributes = state.get("attributes")
    constraints = state.get("constraints")
    user_hypotheses = state.get("starting_hypotheses")
    user_literature = state.get("literature")

    # extract user configuration for workflow
    initial_hypotheses_count = state.get("initial_hypotheses_count")
    max_iterations = state.get("max_iterations")
    evolution_max_count = state.get("evolution_max_count")
    mcp_available = state.get("mcp_available", False)
    pubmed_available = state.get("pubmed_available", False)

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "supervisor_start",
            {
                "message": "Analyzing research goal and creating plan...",
                "progress": PROGRESS_SUPERVISOR_START,
            },
        )

    # call llm to create research plan with all context
    prompt, schema = get_supervisor_prompt(
        research_goal=research_goal,
        preferences=preferences,
        attributes=attributes,
        constraints=constraints,
        user_hypotheses=user_hypotheses,
        user_literature=user_literature,
        initial_hypotheses_count=initial_hypotheses_count,
        max_iterations=max_iterations,
        evolution_max_count=evolution_max_count,
        mcp_available=mcp_available,
        pubmed_available=pubmed_available,
    )

    response = await call_llm_json(
        prompt=prompt,
        model_name=state["model_name"],
        max_tokens=EXTENDED_MAX_TOKENS,
        temperature=MEDIUM_TEMPERATURE,
        json_schema=schema,
    )

    supervisor_guidance = {
        "research_goal_analysis": response.get("research_goal_analysis", {}),
        "workflow_plan": response.get("workflow_plan", {}),
        "performance_assessment": response.get("performance_assessment", {}),
        "adjustment_recommendations": response.get("adjustment_recommendations", []),
        "output_preparation": response.get("output_preparation", {}),
    }

    logger.info("Supervisor plan created")

    # Log key insights from supervisor
    goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
    key_areas = goal_analysis.get("key_areas", [])
    if key_areas:
        logger.info(f"Key research areas identified: {', '.join(key_areas[:3])}")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "supervisor_complete",
            {
                "message": "Research plan created",
                "progress": PROGRESS_SUPERVISOR_COMPLETE,
                "key_areas": len(key_areas),
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(llm_calls_delta=1)

    return {
        "supervisor_guidance": supervisor_guidance,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": "Created research plan and workflow guidance",
                "metadata": {"phase": "supervisor", "key_areas": len(key_areas)},
            }
        ],
    }
