"""
Standard generation strategy - generate hypotheses without literature review.

Used when no literature review is available or as fallback.
"""

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


async def generate_standard(
    state: WorkflowState,
    count: int,
    supervisor_guidance: Dict[str, Any],
    preferences: Optional[str],
    attributes: Optional[List[str]],
    user_hypotheses: Optional[List[str]],
) -> List[Hypothesis]:
    """
    generate hypotheses using standard generation (no literature review)

    args:
        state: current workflow state
        count: number of hypotheses to generate
        supervisor_guidance: supervisor's research plan
        preferences: user preferences for hypotheses
        attributes: key attributes to prioritize
        user_hypotheses: user-provided starting hypotheses

    returns:
        list of generated hypotheses with generation_method="standard"
    """
    if count == 0:
        return []

    prompt, schema = get_generation_prompt(
        research_goal=state["research_goal"],
        hypotheses_count=count,
        supervisor_guidance=supervisor_guidance,
        articles_with_reasoning=None,
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
            generation_method="standard",
        )
        hypotheses.append(hypothesis)

    return hypotheses
