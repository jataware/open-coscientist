"""
reflection node - analyzes hypotheses against literature observations.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from ..constants import (
    EXTENDED_MAX_TOKENS,
    LOW_TEMPERATURE,
    PROGRESS_REFLECTION_START,
    PROGRESS_REFLECTION_COMPLETE,
)
from ..llm import call_llm_json
from ..models import Hypothesis
from ..prompts import get_reflection_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def analyze_single_hypothesis(
    hypothesis: Hypothesis,
    articles_with_reasoning: str,
    model_name: str,
    hypothesis_index: int,
    total_count: int,
    run_id: str | None = None,
    tool_registry: Any | None = None,
) -> Optional[Dict[str, Any]]:
    """
    analyze a single hypothesis against literature observations.

    args:
        hypothesis: hypothesis to analyze
        articles_with_reasoning: literature review context
        model_name: llm model to use
        hypothesis_index: index for logging (1-based)
        total_count: total hypotheses count for logging

    returns:
        dict with classification and reasoning, or None if failed
    """
    logger.debug(f"\n→ analyzing hypothesis {hypothesis_index}/{total_count}")

    # pre-fetch INDRA evidence for this hypothesis (non-critical, skip on failure)
    indra_data = await _fetch_indra_for_hypothesis(
        hypothesis.text, tool_registry, hypothesis_index,
    )

    # get reflection prompt (uses formatted text for LLM context)
    prompt, schema = get_reflection_prompt(
        articles_with_reasoning=articles_with_reasoning,
        hypothesis_text=hypothesis.text,
        tool_registry=tool_registry,
        indra_evidence=indra_data.get("prompt_text", ""),
    )

    # save prompt to disk for debugging
    if run_id:
        from ..prompts import save_prompt_to_disk
        save_prompt_to_disk(
            run_id=run_id,
            prompt_name=f"reflection_{hypothesis_index}",
            content=prompt,
            metadata={
                "hypothesis_index": hypothesis_index,
                "total_count": total_count,
                "prompt_length_chars": len(prompt),
            },
        )

    try:
        # call llm
        response = await call_llm_json(
            prompt=prompt,
            model_name=model_name,
            max_tokens=EXTENDED_MAX_TOKENS,
            temperature=LOW_TEMPERATURE,
            json_schema=schema,
        )

        classification = response.get("classification", "neutral")
        reasoning = response.get("reasoning", "")

        logger.debug(f"hypothesis {hypothesis_index} classification: {classification}")

        return {
            "classification": classification,
            "reasoning": reasoning,
            "indra_enrichment_items": indra_data.get("enrichment_items", []),
        }

    except Exception as e:
        logger.error(f"Reflection failed for hypothesis {hypothesis_index}: {e}")
        return None


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
        await state["progress_callback"](
            "reflection_start",
            {
                "message": f"Analyzing {len(hypotheses)} hypotheses against literature...",
                "progress": PROGRESS_REFLECTION_START,
                "hypotheses_count": len(hypotheses),
            },
        )

    # analyze all hypotheses in parallel
    logger.info(f"Running {len(hypotheses)} reflection analyses in parallel")

    tool_registry = state.get("tool_registry")
    analysis_tasks = [
        analyze_single_hypothesis(
            hypothesis=hyp,
            articles_with_reasoning=articles_with_reasoning,
            model_name=state["model_name"],
            hypothesis_index=i + 1,
            total_count=len(hypotheses),
            run_id=state.get("run_id"),
            tool_registry=tool_registry,
        )
        for i, hyp in enumerate(hypotheses)
    ]

    # gather all results
    analysis_results = await asyncio.gather(*analysis_tasks)

    # apply results to hypotheses
    for hypothesis, result in zip(hypotheses, analysis_results):
        if result:
            classification = result.get("classification", "neutral")
            reasoning = result.get("reasoning", "")
            hypothesis.reflection_notes = f"{reasoning}\n\nClassification: {classification}"
            # store knowledge graph evidence in enrichments (yaml-driven, only present for biomedical configs)
            enrichment_items = result.get("indra_enrichment_items", [])
            if enrichment_items:
                hypothesis.enrichments["indra_evidence"] = enrichment_items
        else:
            hypothesis.reflection_notes = "Analysis failed\n\nClassification: neutral"

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "reflection_complete",
            {
                "message": "Reflection analysis complete",
                "progress": PROGRESS_REFLECTION_COMPLETE,
                "hypotheses_count": len(hypotheses),
            },
        )

    logger.info(f"Completed reflection analysis for {len(hypotheses)} hypotheses")

    return {
        "hypotheses": hypotheses,
        "messages": [
            {
                "role": "assistant",
                "content": f"completed reflection analysis for {len(hypotheses)} hypotheses",
                "metadata": {"phase": "reflection"},
            }
        ],
    }


async def _fetch_indra_for_hypothesis(
    hypothesis_text: str,
    tool_registry: Any | None,
    hypothesis_index: int,
) -> Dict[str, Any]:
    """Pre-fetch INDRA knowledge graph evidence for a hypothesis.

    Non-critical: returns empty dict on any failure so reflection
    proceeds without INDRA data if the MCP server or tools are unavailable.

    Returns dict with "prompt_text" (str) and "enrichment_items" (list).
    """
    empty: Dict[str, Any] = {"prompt_text": "", "enrichment_items": []}
    try:
        from .reflection_helpers import fetch_indra_evidence

        result = await fetch_indra_evidence(
            hypothesis_text=hypothesis_text,
            tool_registry=tool_registry,
            max_statements=5,
        )
        prompt_text = result.get("prompt_text", "")
        if prompt_text:
            logger.debug(
                f"hypothesis {hypothesis_index}: fetched INDRA evidence "
                f"({len(prompt_text)} chars, {len(result.get('enrichment_items', []))} items)"
            )
        return result
    except Exception as e:
        logger.debug(f"hypothesis {hypothesis_index}: INDRA fetch skipped: {e}")
        return empty
