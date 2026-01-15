"""
reflection node - analyzes hypotheses against literature observations.
"""

import logging
from typing import Any, Dict

from ..constants import (
    EXTENDED_MAX_TOKENS,
    LOW_TEMPERATURE,
    PROGRESS_REFLECTION_START,
    PROGRESS_REFLECTION_COMPLETE,
)
from ..llm import call_llm_json
from ..prompts import get_reflection_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def reflection_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Analyze each hypothesis against literature observations.

    this node:
    1. for each generated hypothesis, calls the llm with reflection prompt
    2. analyzes if hypothesis provides novel causal explanation
    3. classifies as: already explained, other explanations more likely,
       missing piece, neutral, or disproved
    4. stores reflection metadata on each hypothesis

    args:
        state: current workflow state

    returns:
        dictionary with updated state fields
    """
    logger.debug("\n=== reflection node ===")
    logger.info("Analyzing hypotheses against literature observations")

    # get articles with reasoning from state
    articles_with_reasoning = state.get("articles_with_reasoning")
    if not articles_with_reasoning:
        logger.warning("No articles_with_reasoning in state, skipping reflection")
        return {}

    # get hypotheses from state
    hypotheses = state.get("hypotheses", [])
    if not hypotheses:
        logger.warning("No hypotheses in state, skipping reflection")
        return {}

    logger.debug(f"analyzing {len(hypotheses)} hypotheses against literature")

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"]("reflection_start", {
            "message": f"Analyzing {len(hypotheses)} hypotheses against literature...",
            "progress": PROGRESS_REFLECTION_START,
            "hypotheses_count": len(hypotheses)
        })

    # analyze each hypothesis
    for i, hypothesis in enumerate(hypotheses):
        logger.debug(f"\n→ analyzing hypothesis {i+1}/{len(hypotheses)}")

        # get reflection prompt
        prompt, schema = get_reflection_prompt(
            articles_with_reasoning=articles_with_reasoning,
            hypothesis_text=hypothesis.text
        )

        try:
            # call llm
            response = await call_llm_json(
                prompt=prompt,
                model_name=state["model_name"],
                max_tokens=EXTENDED_MAX_TOKENS,
                temperature=LOW_TEMPERATURE,
                json_schema=schema,
            )

            # store reflection analysis on hypothesis
            classification = response.get("classification", "neutral")
            reasoning = response.get("reasoning", "")

            # concatenate reasoning and classification into reflection_notes
            hypothesis.reflection_notes = f"{reasoning}\n\nClassification: {classification}"

            logger.debug(f"classification: {classification}")

        except Exception as e:
            logger.error(f"Reflection failed for hypothesis {i+1}: {e}")
            # continue with other hypotheses

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"]("reflection_complete", {
            "message": "Reflection analysis complete",
            "progress": PROGRESS_REFLECTION_COMPLETE,
            "hypotheses_count": len(hypotheses)
        })

    logger.info(f"Completed reflection analysis for {len(hypotheses)} hypotheses")

    return {
        "hypotheses": hypotheses,
        "messages": [
            {
                "role": "assistant",
                "content": f"completed reflection analysis for {len(hypotheses)} hypotheses",
                "metadata": {"phase": "reflection"}
            }
        ]
    }
