"""
Debate generation strategy - generate hypotheses through adversarial debates.

Each debate runs multiple turns between experts to generate a single hypothesis.
Multiple debates can run in parallel.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from ...constants import (
    DEBATE_MAX_TURNS,
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    INITIAL_ELO_RATING,
)
from ...llm import call_llm, call_llm_json
from ...models import Hypothesis
from ...prompts import get_debate_generation_prompt
from ...state import WorkflowState

logger = logging.getLogger(__name__)


async def _run_single_debate(
    state: WorkflowState,
    debate_id: Optional[int] = None,
    num_turns: int = DEBATE_MAX_TURNS
) -> Tuple[Hypothesis, str]:
    """
    generate a single hypothesis using multi-turn debate strategy

    args:
        state: current workflow state
        debate_id: id for this debate (used for tracking and identification)
        num_turns: number of debate turns to run (default from constants)

    returns:
        tuple of (single generated Hypothesis object, debate transcript string)
    """
    count = 1  # each debate generates exactly 1 hypothesis
    debate_label = f"debate {debate_id}" if debate_id is not None else "debate"

    supervisor_guidance = state.get("supervisor_guidance")
    preferences = state.get("preferences")
    attributes = state.get("attributes")

    transcript = ""

    for turn in range(1, num_turns + 1):
        is_final = turn == num_turns

        prompt, schema = get_debate_generation_prompt(
            research_goal=state["research_goal"],
            hypotheses_count=count,
            transcript=transcript,
            supervisor_guidance=supervisor_guidance,
            preferences=preferences,
            attributes=attributes,
            is_final_turn=is_final,
        )

        if is_final:
            # final turn: get structured JSON output with higher token limit for accumulated transcript
            # debates generate 1 hypothesis each but with longer context, so scale moderately
            # increased buffer to handle verbose models and Unicode characters
            scaled_max_tokens = min(EXTENDED_MAX_TOKENS + 4000, 20000)

            response = await call_llm_json(
                prompt=prompt,
                model_name=state["model_name"],
                max_tokens=scaled_max_tokens,
                temperature=HIGH_TEMPERATURE,
                json_schema=schema,
            )

            # parse hypothesis from response (should be exactly 1)
            hypotheses_data = response.get("hypotheses", [])
            if not hypotheses_data:
                raise ValueError(f"{debate_label} failed to generate hypothesis")

            hyp_data = hypotheses_data[0]  # take first hypothesis
            hypothesis = Hypothesis(
                text=hyp_data.get("text", ""),
                justification=hyp_data.get("justification"),
                literature_review_used=hyp_data.get("literature_review_used"),
                score=0.0,
                elo_rating=INITIAL_ELO_RATING,
                generation_method="debate",
                debate_id=debate_id,
            )

            return hypothesis, transcript
        else:
            # non-final turn: get conversational response with higher token limit for accumulated transcript
            response_text = await call_llm(
                prompt=prompt,
                model_name=state["model_name"],
                max_tokens=EXTENDED_MAX_TOKENS,
                temperature=HIGH_TEMPERATURE,
            )

            # accumulate to transcript
            transcript += f"\n\nTurn {turn}:\n{response_text}"

    # should not reach here, but raise error as fallback
    raise ValueError(f"{debate_label} ended without final turn")


async def generate_with_debate(
    state: WorkflowState, count: int
) -> Tuple[List[Hypothesis], List[Dict[str, Any]]]:
    """
    generate hypotheses using parallel debate strategy

    each debate generates 1 hypothesis through multi-turn expert discussion

    args:
        state: current workflow state
        count: number of debates to run (= number of hypotheses to generate)

    returns:
        tuple of (debate_hypotheses, debate_transcripts)
    """
    if count == 0:
        return [], []

    logger.info(f"Running {count} parallel debates")

    # run count parallel debates, each generating 1 hypothesis
    debate_tasks = [
        _run_single_debate(state, debate_id=i)
        for i in range(count)
    ]

    debate_results = await asyncio.gather(*debate_tasks)

    # unpack results
    debate_hypotheses = [hyp for hyp, _ in debate_results]
    debate_transcripts = [
        {
            "debate_id": i,
            "transcript": transcript,
            "hypothesis_text": debate_hypotheses[i].text
        }
        for i, (_, transcript) in enumerate(debate_results)
    ]

    logger.info(f"Generated {len(debate_hypotheses)} hypotheses from debates")
    return debate_hypotheses, debate_transcripts
