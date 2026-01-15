"""
Review node - adaptive peer review strategy based on hypothesis count.

- Small batches (≤5): Comparative batch review for differentiated scores
- Large batches (>5): Parallel individual reviews for scalability
"""

import asyncio
import logging
from typing import Any, Dict, List

from ..constants import (
    THINKING_MAX_TOKENS,
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    PROGRESS_REVIEW_START,
    PROGRESS_REVIEW_COMPLETE,
    COMPARATIVE_BATCH_THRESHOLD,
)
from ..llm import call_llm_json
from ..models import Hypothesis, HypothesisReview, create_metrics_update
from ..prompts import get_review_batch_prompt, get_review_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)


async def review_single_hypothesis(
    hypothesis_text: str,
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
) -> HypothesisReview:
    """
    Review a single hypothesis.

    Args:
        hypothesis_text: The hypothesis to review
        research_goal: The research goal for context
        model_name: LLM model to use

    Returns:
        HypothesisReview object
    """
    # Note: meta_review is not available in this function
    # They would need to be passed as parameters if needed
    prompt, schema = get_review_prompt(
        research_goal=research_goal,
        hypothesis_text=hypothesis_text,
        supervisor_guidance=supervisor_guidance,
        meta_review=meta_review,
    )

    response = await call_llm_json(
        prompt=prompt,
        model_name=model_name,
        max_tokens=EXTENDED_MAX_TOKENS,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
    )

    # Calculate overall_score from criterion scores (more consistent than LLM-provided)
    scores = response.get("scores", {})
    if scores:
        overall_score = sum(scores.values()) / len(scores)
    else:
        overall_score = response.get("overall_score", 0.0)

    return HypothesisReview(
        review_summary=response.get("review_summary", ""),
        scores=scores,
        safety_ethical_concerns=response.get("safety_ethical_concerns", ""),
        detailed_feedback=response.get("detailed_feedback", {}),
        constructive_feedback=response.get("constructive_feedback", ""),
        overall_score=overall_score,
    )


async def review_parallel_individual(
    hypotheses: List[Hypothesis],
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
) -> List[HypothesisReview]:
    """
    Review hypotheses in parallel (original approach).

    Each hypothesis is reviewed independently without seeing others.
    Fast but may produce similar scores for high-quality hypotheses.

    Args:
        hypotheses: List of hypotheses to review
        research_goal: Research goal for context
        model_name: LLM model to use

    Returns:
        List of reviews (one per hypothesis)
    """
    review_tasks = [
        review_single_hypothesis(
            hypothesis_text=hyp.text,
            research_goal=research_goal,
            model_name=model_name,
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
        )
        for hyp in hypotheses
    ]

    return await asyncio.gather(*review_tasks)


async def review_comparative_batch(
    hypotheses: List[Hypothesis],
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
) -> List[HypothesisReview]:
    """
    Review hypotheses in a single comparative batch.

    All hypotheses are shown to one LLM call for relative comparison.
    Produces more differentiated scores but limited by token constraints.

    Args:
        hypotheses: List of hypotheses to review
        research_goal: Research goal for context
        model_name: LLM model to use

    Returns:
        List of reviews (one per hypothesis)
    """
    # Format hypotheses for batch review
    hypotheses_list = "\n\n".join([
        f"**Hypothesis {i}:**\n{hyp.text}"
        for i, hyp in enumerate(hypotheses)
    ])

    # Call batch review
    prompt, schema = get_review_batch_prompt(
        research_goal=research_goal,
        hypotheses_list=hypotheses_list,
        supervisor_guidance=supervisor_guidance,
        meta_review=meta_review,
    )

    # scale max_tokens based on hypothesis count in batch
    # base: 18000 (THINKING_MAX_TOKENS), add 1500 per hypothesis beyond 5
    hypothesis_count = len(hypotheses)
    scaled_max_tokens = min(
        THINKING_MAX_TOKENS + (max(0, hypothesis_count - 5) * 1500),
        24000,  # reasonable upper limit for batch review
    )

    response = await call_llm_json(
        prompt=prompt,
        model_name=model_name,
        max_tokens=scaled_max_tokens,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
        max_attempts=7 if hypothesis_count > 10 else 5,  # increase retries for large batches
    )

    # extract reviews from response
    reviews_data = response.get("reviews", [])

    # debug logging
    logger.debug(f"batch review response keys: {list(response.keys())}")
    logger.debug(
        f"reviews_data type: {type(reviews_data)}, length: {len(reviews_data) if isinstance(reviews_data, list) else 'N/A'}"
    )

    if len(reviews_data) != len(hypotheses):
        logger.warning(f"Expected {len(hypotheses)} reviews but got {len(reviews_data)}")

    # Convert to HypothesisReview objects
    reviews = []
    for i in range(len(hypotheses)):
        if i < len(reviews_data):
            review_data = reviews_data[i]
            scores = review_data.get("scores", {})

            # Calculate overall score from criterion scores
            if scores:
                overall_score = sum(scores.values()) / len(scores)
            else:
                overall_score = 0.0

            review = HypothesisReview(
                review_summary=review_data.get("review_summary", ""),
                scores=scores,
                safety_ethical_concerns=review_data.get("safety_ethical_concerns", ""),
                detailed_feedback=review_data.get("detailed_feedback", {}),
                constructive_feedback=review_data.get("constructive_feedback", ""),
                overall_score=overall_score,
            )
            reviews.append(review)
        else:
            # missing review - create empty one
            logger.error(f"No review data for hypothesis {i}")
            reviews.append(
                HypothesisReview(
                    review_summary="Review unavailable",
                    scores={},
                    safety_ethical_concerns="",
                    detailed_feedback={},
                    constructive_feedback="",
                    overall_score=0.0,
                )
            )

    return reviews


async def review_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Review all hypotheses using adaptive strategy.

    Strategy selection:
    - Small batches (≤5): Comparative batch review for differentiated scores
    - Large batches (>5): Parallel individual reviews for scalability

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields
    """
    logger.info("Starting review node")

    hypotheses = state["hypotheses"]
    num_hypotheses = len(hypotheses)

    logger.info(f"Reviewing {num_hypotheses} hypotheses")

    # Choose strategy based on count
    use_comparative = num_hypotheses <= COMPARATIVE_BATCH_THRESHOLD

    if use_comparative:
        logger.info(
            f"Reviewing {num_hypotheses} hypotheses via comparative batch (≤{COMPARATIVE_BATCH_THRESHOLD})"
        )
        strategy_name = "comparative batch"
    else:
        logger.info(
            f"Reviewing {num_hypotheses} hypotheses via parallel individual (>{COMPARATIVE_BATCH_THRESHOLD})"
        )
        strategy_name = "parallel"

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "review_start",
            {
                "message": f"Reviewing {num_hypotheses} hypotheses...",
                "progress": PROGRESS_REVIEW_START,
            },
        )

    # Get supervisor guidance and meta_review from state
    supervisor_guidance = state.get("supervisor_guidance")
    meta_review = state.get("meta_review")

    # Execute chosen strategy
    if use_comparative:
        reviews = await review_comparative_batch(
            hypotheses=hypotheses,
            research_goal=state["research_goal"],
            model_name=state["model_name"],
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
        )
        llm_calls = 1  # Single batch call
    else:
        reviews = await review_parallel_individual(
            hypotheses=hypotheses,
            research_goal=state["research_goal"],
            model_name=state["model_name"],
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
        )
        llm_calls = num_hypotheses  # One call per hypothesis

    # validate reviews before continuing
    invalid_reviews = [i for i, r in enumerate(reviews) if r.review_summary == "Review unavailable"]
    if invalid_reviews:
        error_msg = f"review node failed: {len(invalid_reviews)}/{len(reviews)} reviews invalid"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Attach reviews to hypotheses
    for hypothesis, review in zip(hypotheses, reviews):
        hypothesis.reviews.append(review)
        hypothesis.score = review.overall_score

    logger.info(f"Completed {len(reviews)} reviews using {strategy_name} strategy")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "review_complete",
            {
                "message": f"Completed {len(reviews)} reviews",
                "progress": PROGRESS_REVIEW_COMPLETE,
                "reviews_count": len(reviews),
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(reviews_count_delta=len(reviews), llm_calls_delta=llm_calls)
    logger.debug(
        f"review node creating metrics delta: reviews={len(reviews)}, llm_calls={llm_calls}"
    )

    return {
        "hypotheses": hypotheses,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": f"Reviewed {len(reviews)} hypotheses ({strategy_name})",
                "metadata": {"phase": "review", "strategy": strategy_name},
            }
        ],
    }
