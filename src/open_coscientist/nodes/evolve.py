"""
Evolve node - refine top hypotheses with context-aware evolution.
"""

import asyncio
import json
import logging
import random
from typing import Any, Dict, List

from ..constants import (
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    DUPLICATE_SIMILARITY_THRESHOLD,
    PROGRESS_EVOLVE_START,
    PROGRESS_EVOLVE_COMPLETE,
)
from ..llm import call_llm_json
from ..models import Hypothesis, create_metrics_update
from ..prompts import load_prompt_with_schema
from ..state import WorkflowState

logger = logging.getLogger(__name__)


def sample_context_hypotheses(
    all_hypotheses: List[Hypothesis],
    exclude_hypothesis: Hypothesis,
    max_context: int = 15
) -> List[str]:
    """
    Strategically sample a subset of other hypotheses for evolution context.

    To prevent token explosion with large hypothesis pools, we sample:
    - Top 5 by Elo rating (avoid copying winners)
    - Up to 10 random samples from the rest (diversity check)

    args:
        all_hypotheses: all hypotheses being evolved
        exclude_hypothesis: the hypothesis being evolved (exclude from context)
        max_context: maximum context hypotheses to include (default 15)

    returns:
        List of hypothesis texts to use as context
    """
    # filter out the current hypothesis
    others = [h for h in all_hypotheses if h.text != exclude_hypothesis.text]

    if len(others) <= max_context:
        # small pool, include all
        return [h.text for h in others]

    # sort by Elo rating (descending)
    others_sorted = sorted(others, key=lambda h: h.elo_rating, reverse=True)

    # take top 5 by Elo (the best ones to avoid copying)
    top_performers = others_sorted[:5]
    remaining = others_sorted[5:]

    # sample up to 10 more from the rest
    sample_count = min(10, len(remaining))
    sampled_others = random.sample(remaining, sample_count) if remaining else []

    # combine: top 5 + sampled 10 = max 15
    context_hypotheses = top_performers + sampled_others

    logger.debug(
        f"sampled {len(context_hypotheses)} context hypotheses "
        f"(top 5 + {len(sampled_others)} random) from {len(others)} total"
    )

    return [h.text for h in context_hypotheses]


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple similarity between two texts.

    This is a basic implementation using word overlap. TODO: For production,
    consider using embeddings or more sophisticated similarity metrics.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score between 0 and 1
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0


async def evolve_single_hypothesis(
    hypothesis: Hypothesis,
    other_hypotheses_texts: List[str],
    meta_review: Dict[str, Any],
    research_goal: str,
    model_name: str,
    removed_duplicates: List[str],
    supervisor_guidance: Dict[str, Any] | None = None,
) -> Hypothesis:
    """
    Evolve a single hypothesis with strategically sampled context to prevent convergence.

    This is the CRITICAL anti-duplicate strategy: we pass a subset of other hypotheses
    (top 5 by Elo + random samples) so the LLM knows what to avoid while keeping
    token budget manageable for large hypothesis pools.

    Args:
        hypothesis: Hypothesis to evolve
        other_hypotheses_texts: Strategically sampled subset of other hypotheses (max 15)
        meta_review: Meta-review insights for strategic guidance
        research_goal: Research goal for context
        model_name: LLM model to use
        removed_duplicates: Previously removed duplicate texts to avoid

    Returns:
        Updated hypothesis with evolved text
    """
    # Log meta review usage with colorful output
    logger.debug("\n=== evolve single hypothesis ===")
    logger.debug("using meta review for evolution")

    # Display meta review details
    common_strengths = meta_review.get("common_strengths", [])
    common_weaknesses = meta_review.get("common_weaknesses", [])
    strategic_recommendations = meta_review.get("strategic_recommendations", [])
    emerging_themes = meta_review.get("emerging_themes", [])

    if common_strengths:
        logger.debug(f"common Strengths ({len(common_strengths)}):")
        for strength in common_strengths[:3]:  # Show first 3
            logger.debug(f"- {strength[:100]}{'...' if len(strength) > 100 else ''}")

    if common_weaknesses:
        logger.debug(f"common Weaknesses ({len(common_weaknesses)}):")
        for weakness in common_weaknesses[:3]:  # Show first 3
            logger.debug(f"- {weakness[:100]}{'...' if len(weakness) > 100 else ''}")

    if strategic_recommendations:
        logger.debug(f"strategic Recommendations ({len(strategic_recommendations)}):")
        for rec in strategic_recommendations[:3]:  # Show first 3
            logger.debug(f"- {rec}")

    if emerging_themes:
        logger.debug(f"emerging Themes ({len(emerging_themes)}):")
        for theme in emerging_themes[:3]:  # Show first 3
            logger.debug(f"- {theme}")

    # Get latest review feedback
    review_feedback = ""
    if hypothesis.reviews:
        latest_review = hypothesis.reviews[-1]
        review_feedback = json.dumps(
            {
                "overall_score": latest_review.overall_score,
                "review_summary": latest_review.review_summary,
                "constructive_feedback": latest_review.constructive_feedback,
                "scores": latest_review.scores,
            },
            indent=2,
        )

    # Format meta-review insights
    meta_review_insights = json.dumps(
        {
            "common_strengths": meta_review.get("common_strengths", []),
            "common_weaknesses": meta_review.get("common_weaknesses", []),
            "strategic_recommendations": meta_review.get("strategic_recommendations", []),
            "emerging_themes": meta_review.get("emerging_themes", []),
        },
        indent=2,
    )

    # Format supervisor guidance for evolution
    supervisor_guidance_text = ""
    if supervisor_guidance and isinstance(supervisor_guidance, dict):
        workflow_plan = supervisor_guidance.get("workflow_plan", {})
        evolution_phase = workflow_plan.get("evolution_phase", {})

        if evolution_phase:
            guidance_sections = []
            guidance_sections.append("## Supervisor Guidance for Evolution\n")
            if evolution_phase.get("refinement_priorities"):
                priorities = evolution_phase["refinement_priorities"]
                if isinstance(priorities, list):
                    priorities = ", ".join(priorities)
                guidance_sections.append(f"**Refinement Priorities:** {priorities}\n")
            if evolution_phase.get("iteration_strategy"):
                guidance_sections.append(
                    f"**Iteration Strategy:** {evolution_phase['iteration_strategy']}\n"
                )
            guidance_sections.append(
                "\nUse this guidance to align your refinement with the research plan.\n"
            )
            supervisor_guidance_text = "".join(guidance_sections)

    # Build context-aware evolution prompt
    prompt, schema = load_prompt_with_schema(
        "evolution",
        {
            "original_hypothesis": hypothesis.text,
            "review_feedback": review_feedback,
            "meta_review_insights": meta_review_insights,
            "supervisor_guidance": supervisor_guidance_text,
        },
    )

    # Add critical diversity instruction
    other_hyps_formatted = "\n".join([f"- {text[:200]}..." for text in other_hypotheses_texts])
    removed_dups_formatted = "\n".join(
        [f"- {text[:200]}..." for text in removed_duplicates[-5:]]
    )  # Last 5

    diversity_instruction = f"""

## CRITICAL: Preserve Diversity

**Other hypotheses being evolved simultaneously:**
{other_hyps_formatted if other_hyps_formatted else "None"}

**Previously removed duplicates (DO NOT recreate these):**
{removed_dups_formatted if removed_dups_formatted else "None"}

**CRITICAL REQUIREMENT:** Your refined hypothesis MUST remain DISTINCT from:
1. All other hypotheses listed above
2. Previously removed duplicates

DO NOT:
- Use the same biomarker/methodology as other hypotheses
- Make only trivial wording changes
- Converge toward similar concepts

DO:
- Maintain the unique aspects of this hypothesis
- Explore different mechanisms or approaches
- Preserve conceptual diversity
"""

    full_prompt = prompt + diversity_instruction

    # fixed token budget since we strategically sample max 15 context hypotheses
    # base: 8000, add 800 per context hypothesis (max 15 × 800 = 12,000)
    # total: 8000 + 12,000 = 20,000 tokens (fixed budget for any pool size)
    scaled_max_tokens = min(
        EXTENDED_MAX_TOKENS + (len(other_hypotheses_texts) * 800),
        20000
    )

    logger.debug(
        f"evolution token budget: {scaled_max_tokens} "
        f"({len(other_hypotheses_texts)} context hypotheses)"
    )

    # Call LLM to evolve hypothesis
    response = await call_llm_json(
        prompt=full_prompt,
        model_name=model_name,
        max_tokens=scaled_max_tokens,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
        max_attempts=7,  # increase retries for evolution (critical node)
    )

    # Extract fields from response (match evolution.md prompt format)
    refined_text = response.get("refined_hypothesis_text", hypothesis.text)
    refinement_summary = response.get("refinement_summary", "No refinement summary provided")

    # Check if hypothesis actually changed
    if refined_text == hypothesis.text:
        logger.warning("Evolution returned unchanged hypothesis")
        return hypothesis, None  # Keep original, no evolution details

    # Check similarity to other hypotheses
    max_similarity = 0.0
    most_similar_text = None
    for other_text in other_hypotheses_texts:
        similarity = calculate_text_similarity(refined_text, other_text)
        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_text = other_text

    # If too similar, keep original
    if max_similarity > DUPLICATE_SIMILARITY_THRESHOLD:
        logger.warning(
            f"Evolution created near-duplicate! Similarity: {max_similarity:.2f}. "
            f"Keeping original hypothesis."
        )
        logger.debug(f"original: {hypothesis.text[:100]}...")
        logger.debug(f"similar to: {most_similar_text[:100]}...")
        return hypothesis, None  # Keep original, no evolution details

    # Update hypothesis
    original_text = hypothesis.text
    hypothesis.text = refined_text
    hypothesis.evolution_history.append(original_text)

    logger.debug(f"evolved hypothesis (max similarity: {max_similarity:.2f})")

    # Return both hypothesis and evolution details
    evolution_detail = {
        "original": original_text,
        "evolved": refined_text,
        "rationale": refinement_summary,
        "changes": [],  # Not in evolution.md prompt format
        "improvements": [],  # Not in evolution.md prompt format
    }

    return hypothesis, evolution_detail


async def evolve_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Evolve top-k hypotheses with context-aware refinement.

    This node implements the most impactful anti-duplicate strategy:
    context-aware evolution where each LLM call knows what all other
    hypotheses are to prevent convergence.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields (evolved hypotheses)
    """
    hypotheses = state["hypotheses"]
    evolution_max_count = state.get("evolution_max_count", 10)

    # Calculate actual number to evolve (may be less than max if fewer hypotheses available)
    actual_count = min(len(hypotheses), evolution_max_count)

    logger.info(f"Evolving top {actual_count} hypotheses")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "evolve_start",
            {
                "message": f"Evolving top {actual_count} hypotheses...",
                "progress": PROGRESS_EVOLVE_START,
            },
        )

    # Get top-k hypotheses
    top_k = hypotheses[:evolution_max_count]

    logger.info(
        f"Evolving {len(top_k)} hypotheses with strategic context sampling "
        f"(max 15 context hypotheses per evolution)"
    )

    # Get previously removed duplicates
    removed_duplicates = [
        dup.get("text", "") for dup in state.get("removed_duplicates", [])
    ]

    # Get supervisor guidance from state
    supervisor_guidance = state.get("supervisor_guidance")

    # Evolve each hypothesis with strategically sampled context (PARALLEL)
    # instead of including ALL other hypotheses, we sample a subset to control token budget
    evolution_tasks = [
        evolve_single_hypothesis(
            hypothesis=hyp,
            other_hypotheses_texts=sample_context_hypotheses(
                all_hypotheses=top_k,
                exclude_hypothesis=hyp,
                max_context=15  # cap at 15 for fixed token budget
            ),
            meta_review=state.get("meta_review", {}),
            research_goal=state["research_goal"],
            model_name=state["model_name"],
            removed_duplicates=removed_duplicates,
            supervisor_guidance=supervisor_guidance,
        )
        for hyp in top_k
    ]

    results = await asyncio.gather(*evolution_tasks)

    # Unpack results: (hypothesis, evolution_detail or None)
    evolved_hypotheses = []
    evolution_details = []

    for hyp, detail in results:
        evolved_hypotheses.append(hyp)
        if detail is not None:  # Only add if hypothesis actually evolved
            evolution_details.append(detail)

    # Keep ONLY the evolved hypotheses (discard lower-ranked ones)
    # This makes evolution_max_count the final pool size
    original_count = len(hypotheses)
    hypotheses = evolved_hypotheses
    discarded_count = original_count - len(evolved_hypotheses)
    logger.info(
        f"Keeping only {len(hypotheses)} evolved hypotheses (discarded {discarded_count} lower-ranked)"
    )

    logger.info(
        f"Evolved {len(evolved_hypotheses)} hypotheses, {len(evolution_details)} with changes"
    )

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "evolve_complete",
            {
                "message": f"Evolved {len(evolved_hypotheses)} hypotheses",
                "progress": PROGRESS_EVOLVE_COMPLETE,
                "evolved_count": len(evolved_hypotheses),
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(
        llm_calls_delta=len(evolved_hypotheses), evolutions_count_delta=len(evolved_hypotheses)
    )
    logger.debug(
        f"evolve node creating metrics delta: evolutions={len(evolved_hypotheses)}, llm_calls={len(evolved_hypotheses)}"
    )

    return {
        "hypotheses": hypotheses,
        "evolution_details": evolution_details,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": f"Evolved {len(evolved_hypotheses)} hypotheses",
                "metadata": {"phase": "evolve", "evolved_count": len(evolved_hypotheses)},
            }
        ],
    }
