"""
Standard literature generation strategy - generate hypotheses using pre-processed literature review.

Uses the output from the literature review node (articles_with_reasoning)
to generate hypotheses in a single LLM call.
"""

import logging
from typing import Any, Dict, List, Optional

from ...constants import (
    DEFAULT_MAX_TOKENS,
    HIGH_TEMPERATURE,
    INITIAL_ELO_RATING,
)
from ...llm import call_llm_json
from ...models import Hypothesis
from ...prompts import get_generation_prompt
from ...state import WorkflowState

logger = logging.getLogger(__name__)


async def generate_with_literature(
    state: WorkflowState,
    count: int,
    supervisor_guidance: Dict[str, Any],
    articles_with_reasoning: str,
    preferences: Optional[str],
    attributes: Optional[List[str]],
    user_hypotheses: Optional[List[str]],
) -> List[Hypothesis]:
    """
    generate hypotheses using pre-processed literature review

    uses articles_with_reasoning from the literature review node
    generates all hypotheses in a single LLM call

    args:
        state: current workflow state
        count: number of hypotheses to generate
        supervisor_guidance: supervisor's research plan
        articles_with_reasoning: pre-processed literature review summary
        preferences: user preferences for hypotheses
        attributes: key attributes to prioritize
        user_hypotheses: user-provided starting hypotheses

    returns:
        list of generated hypotheses with generation_method="literature"
    """
    if count == 0:
        return []

    logger.info(f"Generating {count} hypotheses with pre-processed literature review")

    prompt, schema = get_generation_prompt(
        research_goal=state["research_goal"],
        hypotheses_count=count,
        supervisor_guidance=supervisor_guidance,
        articles_with_reasoning=articles_with_reasoning,
        preferences=preferences,
        attributes=attributes,
        user_hypotheses=user_hypotheses,
        instructions=None,
    )

    # scale max_tokens based on hypothesis count
    scaled_max_tokens = min(
        DEFAULT_MAX_TOKENS + (count * 600),
        16000
    )

    response = await call_llm_json(
        prompt=prompt,
        model_name=state["model_name"],
        max_tokens=scaled_max_tokens,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
        max_attempts=7 if count > 10 else 5,
    )

    hypotheses = []
    for hyp_data in response.get("hypotheses", []):
        hypothesis = Hypothesis(
            text=hyp_data.get("text", ""),
            justification=hyp_data.get("justification"),
            literature_review_used=hyp_data.get("literature_review_used"),
            score=0.0,
            elo_rating=INITIAL_ELO_RATING,
            generation_method="literature",
        )
        hypotheses.append(hypothesis)

    logger.info(f"Generated {len(hypotheses)} hypotheses from literature")
    return hypotheses
