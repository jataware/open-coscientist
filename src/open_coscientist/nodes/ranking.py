"""
Ranking node - Elo-based pairwise comparison of hypotheses.
"""

import asyncio
import hashlib
import logging
import random
from typing import Any, Dict, Tuple

from ..constants import (
    INITIAL_ELO_RATING,
    ELO_K_FACTOR,
    THINKING_MAX_TOKENS,
    LOW_TEMPERATURE,
    MAX_CONCURRENT_LLM_CALLS,
)
from ..llm import call_llm_json
from ..models import Hypothesis, create_metrics_update
from ..prompts import get_ranking_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent LLM calls (avoid rate limits)
_ranking_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)


def calculate_elo_update(
    winner_elo: int, loser_elo: int, k_factor: int = ELO_K_FACTOR
) -> Tuple[int, int]:
    """
    Calculate updated Elo ratings for winner and loser.

    Args:
        winner_elo: Current Elo rating of winner
        loser_elo: Current Elo rating of loser
        k_factor: K-factor for Elo calculation (default 24)

    Returns:
        Tuple of (new_winner_elo, new_loser_elo)
    """
    # Calculate expected scores
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

    # Calculate new ratings
    new_winner_elo = winner_elo + k_factor * (1 - expected_winner)
    new_loser_elo = loser_elo + k_factor * (0 - expected_loser)

    return int(new_winner_elo), int(new_loser_elo)


async def judge_matchup(
    hypothesis_a: Hypothesis,
    hypothesis_b: Hypothesis,
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Have LLM judge which hypothesis is superior.

    Args:
        hypothesis_a: First hypothesis
        hypothesis_b: Second hypothesis
        research_goal: Research goal for context
        model_name: LLM model to use

    Returns:
        Tuple of (winner, full_response) where winner is "a" or "b"
    """
    # Extract review data if available
    review_a = None
    review_b = None
    if hypothesis_a.reviews:
        latest_review_a = hypothesis_a.reviews[-1]
        review_a = {
            "scores": latest_review_a.scores,
            "overall_score": latest_review_a.overall_score,
        }
    if hypothesis_b.reviews:
        latest_review_b = hypothesis_b.reviews[-1]
        review_b = {
            "scores": latest_review_b.scores,
            "overall_score": latest_review_b.overall_score,
        }

    # Extract reflection notes if available
    reflection_notes_a = hypothesis_a.reflection_notes
    reflection_notes_b = hypothesis_b.reflection_notes

    logger.debug("\n→ Ranking Tournament Matchup")

    if reflection_notes_a:
        # extract classification from notes
        classification_a = "unknown"
        if "Classification:" in reflection_notes_a:
            classification_a = (
                reflection_notes_a.split("Classification:")[-1].strip().split("\n")[0]
            )
        logger.debug(
            f"hypothesis A: has reflection ({len(reflection_notes_a)} chars, classification: {classification_a})"
        )
        logger.debug(f"hypothesis A reflection: {reflection_notes_a[:200]}...")
    else:
        logger.debug("hypothesis A: missing reflection notes")

    if reflection_notes_b:
        # extract classification from notes
        classification_b = "unknown"
        if "Classification:" in reflection_notes_b:
            classification_b = (
                reflection_notes_b.split("Classification:")[-1].strip().split("\n")[0]
            )
        logger.debug(
            f"hypothesis B: has reflection ({len(reflection_notes_b)} chars, classification: {classification_b})"
        )
        logger.debug(f"hypothesis B reflection: {reflection_notes_b[:200]}...")
    else:
        logger.debug("hypothesis B: missing reflection notes")

    prompt, schema = get_ranking_prompt(
        research_goal=research_goal,
        hypothesis_a=hypothesis_a.text,
        hypothesis_b=hypothesis_b.text,
        supervisor_guidance=supervisor_guidance,
        review_a=review_a,
        review_b=review_b,
        reflection_notes_a=reflection_notes_a,
        reflection_notes_b=reflection_notes_b,
    )

    if reflection_notes_a or reflection_notes_b:
        if "Reflection Notes" in prompt:
            logger.debug("prompt includes 'Reflection Notes' section")
        else:
            logger.debug("warning: Reflection notes provided but not found in prompt")

    # Use semaphore to limit concurrent calls (avoid rate limits)
    async with _ranking_semaphore:
        response = await call_llm_json(
            prompt=prompt,
            model_name=model_name,
            max_tokens=THINKING_MAX_TOKENS,
            temperature=LOW_TEMPERATURE,
            json_schema=schema,
        )

    winner = response.get("winner", "a").lower()
    if winner not in ["a", "b"]:
        logger.warning(f"Invalid winner '{winner}', defaulting to 'a'")
        winner = "a"

    return winner, response


async def ranking_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Run tournament-style pairwise comparisons with Elo rating updates.

    This node runs multiple rounds of random pairwise matchups where an LLM
    judges which hypothesis is superior. Elo ratings are updated after each
    matchup to reflect relative quality.

    Tournament rounds = len(hypotheses) * 1 (can be adjusted)

    deterministic seeding: the random pairings are seeded using research_goal
    and current_iteration to ensure cache consistency across runs. this allows
    identical inputs to produce identical tournament results, enabling proper
    cache hits in subsequent iterations.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields (hypotheses sorted by Elo)
    """
    hypotheses = state["hypotheses"]
    logger.info(f"Starting ranking tournament with {len(hypotheses)} hypotheses")

    hypotheses_with_reflection = sum(1 for h in hypotheses if h.reflection_notes)
    logger.debug("\n=== ranking tournament debug ===")
    logger.debug(f"total hypotheses: {len(hypotheses)}")
    logger.debug(
        f"hypotheses with reflection notes: {hypotheses_with_reflection}/{len(hypotheses)}"
    )

    if hypotheses_with_reflection == 0:
        logger.debug("warning: No hypotheses have reflection notes!")
    elif hypotheses_with_reflection < len(hypotheses):
        logger.debug("warning: Some hypotheses missing reflection notes")
    else:
        logger.debug("all hypotheses have reflection notes")

    if len(hypotheses) < 2:
        logger.warning("Need at least 2 hypotheses for tournament")
        return {"hypotheses": hypotheses}

    # Sort hypotheses by review score before tournament
    # This provides initial ordering based on review scores
    # Use hypothesis text as tiebreaker for deterministic ordering when scores are equal
    hypotheses.sort(key=lambda h: (h.score, h.text), reverse=True)
    logger.info(f"Sorted hypotheses by review score (top score: {hypotheses[0].score:.2f})")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "tournament_start",
            {"message": f"Running tournament with {len(hypotheses)} hypotheses...", "progress": 65},
        )

    # Initialize Elo ratings if not already set
    for hyp in hypotheses:
        if hyp.elo_rating == INITIAL_ELO_RATING:  # Default value from dataclass
            hyp.elo_rating = INITIAL_ELO_RATING

    # Calculate number of tournament rounds
    tournament_rounds = len(hypotheses) * 1
    logger.info(f"Running {tournament_rounds} tournament rounds")

    # Get supervisor guidance from state
    supervisor_guidance = state.get("supervisor_guidance")

    # Set deterministic random seed based on research goal and iteration
    # this ensures same inputs produce same tournament pairings for cache consistency
    # use hashlib instead of hash() for deterministic results across python processes
    research_goal = state["research_goal"]
    current_iteration = state.get("current_iteration", 0)
    seed_string = f"{research_goal}_{current_iteration}"
    seed = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
    random.seed(seed)

    # Prepare all random pairwise matchups and judge them in parallel
    pairings = [tuple(random.sample(hypotheses, 2)) for _ in range(tournament_rounds)]
    results = await asyncio.gather(
        *[
            judge_matchup(a, b, state["research_goal"], state["model_name"], supervisor_guidance)
            for a, b in pairings
        ]
    )

    # Apply Elo updates based on judged results and collect matchup details
    llm_calls = tournament_rounds
    matchup_details = []

    for (hyp_a, hyp_b), (winner, response) in zip(pairings, results):
        winner_hyp, loser_hyp = (hyp_a, hyp_b) if winner == "a" else (hyp_b, hyp_a)
        old_winner_elo = winner_hyp.elo_rating
        old_loser_elo = loser_hyp.elo_rating

        new_winner_elo, new_loser_elo = calculate_elo_update(
            winner_elo=winner_hyp.elo_rating,
            loser_elo=loser_hyp.elo_rating,
            k_factor=ELO_K_FACTOR
        )
        logger.debug(
            f"Matchup result: Winner {winner_hyp.elo_rating} → {new_winner_elo}, "
            f"Loser {loser_hyp.elo_rating} → {new_loser_elo}"
        )

        # Store matchup details for display
        # Extract reasoning from response (can be decision_summary or judgment_explanation)
        reasoning = response.get("decision_summary", "")
        if not reasoning and "judgment_explanation" in response:
            # Fallback: combine judgment details if decision_summary is missing
            judgment = response["judgment_explanation"]
            reasoning = " | ".join([f"{k}: {v}" for k, v in judgment.items() if v])
        if not reasoning:
            reasoning = "No reasoning provided"

        matchup_details.append(
            {
                "hypothesis_a": hyp_a.text[:200] + "..." if len(hyp_a.text) > 200 else hyp_a.text,
                "hypothesis_b": hyp_b.text[:200] + "..." if len(hyp_b.text) > 200 else hyp_b.text,
                "winner": winner,
                "reasoning": reasoning,
                "confidence": response.get("confidence_level", "Unknown"),
                "winner_elo_before": old_winner_elo,
                "winner_elo_after": new_winner_elo,
                "loser_elo_before": old_loser_elo,
                "loser_elo_after": new_loser_elo,
            }
        )

        winner_hyp.elo_rating = new_winner_elo
        loser_hyp.elo_rating = new_loser_elo
        winner_hyp.win_count += 1
        loser_hyp.loss_count += 1

    # Sort hypotheses by Elo rating (highest first)
    # Use hypothesis text as tiebreaker for deterministic ordering when Elo ratings are equal
    hypotheses.sort(key=lambda h: (h.elo_rating, h.text), reverse=True)

    logger.info(f"Tournament complete. Top Elo: {hypotheses[0].elo_rating}")
    logger.info(f"Top hypothesis: {hypotheses[0].text[:100]}...")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "tournament_complete",
            {
                "message": f"Tournament complete ({tournament_rounds} rounds)",
                "progress": 80,
                "top_elo": hypotheses[0].elo_rating,
                "top_hypothesis": hypotheses[0].text[:200],
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(
        llm_calls_delta=llm_calls, tournaments_count_delta=tournament_rounds
    )
    logger.debug(
        f"ranking node creating metrics delta: tournaments={tournament_rounds}, llm_calls={llm_calls}"
    )

    return {
        "hypotheses": hypotheses,  # Now sorted by Elo rating
        "tournament_matchups": matchup_details,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": f"Completed {tournament_rounds} tournament rounds",
                "metadata": {
                    "phase": "ranking",
                    "rounds": tournament_rounds,
                    "top_elo": hypotheses[0].elo_rating,
                },
            }
        ],
    }
