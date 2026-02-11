"""
Prompt loading and template substitution utilities.

All prompts are stored as markdown files in the prompts/ directory.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from .schemas import get_schema_for_prompt

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# helper functions for saving prompts to disk


def get_prompt_save_path(run_id: str, prompt_name: str) -> Path:
    """
    Get path for saving a filled-in prompt to disk for debugging

    Ensures the output directory exists and returns the full path

    args:
        run_id: unique run identifier (from state)
        prompt_name: descriptive name for the prompt file (e.g., "review_batch", "literature_synthesis")

    returns:
        Path object for the prompt file location

    example:
        path = get_prompt_save_path("abc123", "review_batch")
        # returns Path(".coscientist_prompts/abc123/review_batch.txt")
    """
    prompts_dir = Path(".coscientist_prompts") / run_id
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # ensure .txt extension
    if not prompt_name.endswith(".txt"):
        prompt_name = f"{prompt_name}.txt"

    return prompts_dir / prompt_name


def save_prompt_to_disk(
    run_id: str, prompt_name: str, content: str, metadata: Dict[str, Any] | None = None
) -> bool:
    """
    Save a filled-in prompt to disk for debugging

    args:
        run_id: unique run identifier
        prompt_name: descriptive name for the prompt file
        content: the filled-in prompt content
        metadata: optional dict of metadata to append (e.g., token counts, config)

    returns:
        True if saved successfully, False otherwise
    """
    try:
        path = get_prompt_save_path(run_id, prompt_name)

        with open(path, "w") as f:
            f.write(content)

            # append metadata if provided
            if metadata:
                f.write("\n\n=== METADATA (by save_prompt_to_disk) ===\n")
                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")

        logger.debug(f"Saved prompt to: {path}")
        return True

    except Exception as e:
        logger.warning(f"Failed to save prompt to disk: {e}")
        return False


def load_prompt(prompt_name: str, variables: Dict[str, Any] | None = None) -> str:
    """
    Load a prompt from a markdown file and substitute variables.

    Args:
        prompt_name: Name of the prompt file (without .md extension)
        variables: Dictionary of variables to substitute (e.g., {"research_goal": "..."})

    Returns:
        Formatted prompt string with variables substituted

    Example:
        >>> load_prompt("generation", {"research_goal": "Cure cancer", "hypotheses_count": 5})
    """
    prompt_path = _PROMPTS_DIR / f"{prompt_name}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    # Read the prompt template
    prompt_template = prompt_path.read_text()

    # Substitute variables if provided
    if variables:
        prompt_template = substitute_variables(prompt_template, variables)

    return prompt_template


def load_prompt_with_schema(
    prompt_name: str, variables: Dict[str, Any] | None = None
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Load a prompt and its associated JSON schema.

    Args:
        prompt_name: Name of the prompt file (without .md extension)
        variables: Dictionary of variables to substitute (e.g., {"research_goal": "..."})

    Returns:
        Tuple of (formatted prompt string, JSON schema dict or None)

    Example:
        >>> prompt, schema = load_prompt_with_schema("generation", {"research_goal": "Cure cancer"})
    """
    prompt = load_prompt(prompt_name, variables)
    schema = get_schema_for_prompt(prompt_name)
    return prompt, schema


def substitute_variables(template: str, variables: Dict[str, Any]) -> str:
    """
    Substitute {{variable}} placeholders in a template string.

    Args:
        template: Template string with {{variable}} placeholders
        variables: Dictionary mapping variable names to values

    Returns:
        Template with all variables substituted

    Example:
        >>> substitute_variables("Hello {{name}}", {"name": "World"})
        "Hello World"
    """

    def replacer(match: re.Match) -> str:
        var_name = match.group(1).strip()
        value = variables.get(var_name, f"{{{{MISSING:{var_name}}}}}")
        return str(value)

    # Replace {{variable}} patterns
    return re.sub(r"\{\{([^}]+)\}\}", replacer, template)


# Convenience functions for common prompts
def get_generation_prompt(
    research_goal: str,
    hypotheses_count: int,
    supervisor_guidance: Dict[str, Any] | None = None,
    articles_with_reasoning: str | None = None,
    preferences: str | None = None,
    attributes: str | None = None,
    user_hypotheses: str | None = None,
    instructions: str | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Get the hypothesis generation prompt and schema.

    If articles_with_reasoning is provided, uses the literature review prompt.
    Otherwise, uses the debate generation prompt.
    """
    # determine which prompt to use based on whether literature review is available
    use_literature_prompt = bool(articles_with_reasoning)
    prompt_name = (
        "generation_debate_and_literature" if use_literature_prompt else "generation_after_debate"
    )

    # prepare common variables for both prompts
    variables = {
        "goal": research_goal,
        "hypotheses_count": hypotheses_count,
        "preferences": preferences
        or "Novel, testable, scientifically sound, specific, and diverse hypotheses",
        "attributes": (
            ", ".join(attributes)
            if attributes and isinstance(attributes, list)
            else (attributes or "N/A")
        ),
        "user_hypotheses": (
            "\n".join(f"- {hyp}" for hyp in user_hypotheses)
            if user_hypotheses and isinstance(user_hypotheses, list)
            else (user_hypotheses or "N/A")
        ),
        "instructions": instructions
        or f"Generate {hypotheses_count} diverse and novel hypotheses.",
    }

    # add literature-specific variable if using literature prompt
    if use_literature_prompt:
        variables["articles_with_reasoning"] = articles_with_reasoning or ""

    # format supervisor guidance if available and has content
    if supervisor_guidance and isinstance(supervisor_guidance, dict):
        guidance_sections = []
        has_content = False

        # add key research areas
        goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
        key_areas = goal_analysis.get("key_areas", [])
        if key_areas:
            if not has_content:
                guidance_sections.append("## Supervisor Guidance\n")
                guidance_sections.append(
                    "The Supervisor Agent has analyzed the research goal and provided the following guidance to inform your hypothesis generation:\n"
                )
                has_content = True
            guidance_sections.append("### Key Research Areas\n")
            for area in key_areas:
                guidance_sections.append(f"- {area}\n")

        # add generation phase guidance
        workflow_plan = supervisor_guidance.get("workflow_plan", {})
        generation_phase = workflow_plan.get("generation_phase", {})
        if generation_phase:
            if not has_content:
                guidance_sections.append("## Supervisor Guidance\n")
                guidance_sections.append(
                    "The Supervisor Agent has analyzed the research goal and provided the following guidance to inform your hypothesis generation:\n"
                )
                has_content = True
            guidance_sections.append("\n### Generation Phase Guidance\n")
            if generation_phase.get("focus_areas"):
                focus_areas = generation_phase["focus_areas"]
                if isinstance(focus_areas, list):
                    focus_areas = ", ".join(focus_areas)
                guidance_sections.append(f"**Focus Areas:** {focus_areas}\n")
            if generation_phase.get("diversity_targets"):
                guidance_sections.append(
                    f"**Diversity Targets:** {generation_phase['diversity_targets']}\n"
                )
            if generation_phase.get("quantity_target"):
                guidance_sections.append(
                    f"**Quantity Target:** {generation_phase['quantity_target']}\n"
                )

        if has_content:
            guidance_sections.append(
                "\nUse this guidance to ensure your hypotheses align with the research plan and explore the identified key areas.\n"
            )
            variables["supervisor_guidance"] = "".join(guidance_sections)
        else:
            variables["supervisor_guidance"] = ""
    else:
        variables["supervisor_guidance"] = ""

    return load_prompt_with_schema(prompt_name, variables)


def get_review_prompt(
    research_goal: str,
    hypothesis_text: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the hypothesis review prompt and schema."""
    variables = {"research_goal": research_goal, "hypothesis_text": hypothesis_text}

    # Add supervisor guidance if available
    variables["supervisor_guidance"] = _format_supervisor_guidance_for_review(supervisor_guidance)

    # Add meta-review context if available (for re-reviewing evolved hypotheses)
    variables["meta_review_context"] = _format_meta_review_context(meta_review)

    return load_prompt_with_schema("review", variables)


def get_review_batch_prompt(
    research_goal: str,
    hypotheses_list: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the comparative batch hypothesis review prompt and schema."""
    variables = {"research_goal": research_goal, "hypotheses_list": hypotheses_list}

    # Add supervisor guidance if available
    variables["supervisor_guidance"] = _format_supervisor_guidance_for_review(supervisor_guidance)

    # Add meta-review context if available (for re-reviewing evolved hypotheses)
    variables["meta_review_context"] = _format_meta_review_context(meta_review)

    return load_prompt_with_schema("review_batch", variables)


def get_evolution_prompt(
    original_hypothesis: str, review_feedback: str, meta_review_insights: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the hypothesis evolution prompt and schema."""
    return load_prompt_with_schema(
        "evolution",
        {
            "original_hypothesis": original_hypothesis,
            "review_feedback": review_feedback,
            "meta_review_insights": meta_review_insights,
        },
    )


def get_ranking_prompt(
    research_goal: str,
    hypothesis_a: str,
    hypothesis_b: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    review_a: Dict[str, Any] | None = None,
    review_b: Dict[str, Any] | None = None,
    reflection_notes_a: str | None = None,
    reflection_notes_b: str | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the ranking (and tournament) comparison prompt and schema."""
    variables = {
        "research_goal": research_goal,
        "hypothesis_a": hypothesis_a,
        "hypothesis_b": hypothesis_b,
    }

    # Add supervisor guidance if available
    variables["supervisor_guidance"] = _format_supervisor_guidance_for_ranking(supervisor_guidance)

    # Add review context if available
    variables["review_context"] = _format_review_context(review_a, review_b)

    # Add reflection notes if available
    variables["hypothesis_a_reflection_notes"] = (
        reflection_notes_a or "No reflection notes available."
    )
    variables["hypothesis_b_reflection_notes"] = (
        reflection_notes_b or "No reflection notes available."
    )

    return load_prompt_with_schema("ranking", variables)


def get_meta_review_prompt(
    research_goal: str,
    all_reviews: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    instructions: str | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the meta-review synthesis prompt and schema."""
    variables = {"research_goal": research_goal, "all_reviews": all_reviews}

    # Add supervisor guidance if available
    variables["supervisor_guidance"] = _format_supervisor_guidance_for_meta_review(
        supervisor_guidance
    )

    return load_prompt_with_schema("meta_review", variables)


def get_proximity_prompt(
    hypotheses: list, supervisor_guidance: Dict[str, Any] | None = None
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the proximity/similarity analysis prompt and schema."""
    import json

    variables = {
        "hypotheses": json.dumps(
            [h["text"] if isinstance(h, dict) else h for h in hypotheses], indent=2
        )
    }

    # Add supervisor guidance if available
    variables["supervisor_guidance"] = _format_supervisor_guidance_for_proximity(
        supervisor_guidance
    )

    return load_prompt_with_schema("proximity", variables)


def get_supervisor_prompt(
    research_goal: str,
    preferences: str | None = None,
    attributes: list[str] | None = None,
    constraints: list[str] | None = None,
    user_hypotheses: list[str] | None = None,
    user_literature: list[str] | None = None,
    initial_hypotheses_count: int | None = None,
    max_iterations: int | None = None,
    evolution_max_count: int | None = None,
    mcp_available: bool = False,
    pubmed_available: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """get the supervisor research planning prompt and schema."""

    # Build pipeline description based on available tools
    lit_review_description = ""
    if pubmed_available or mcp_available:
        lit_review_description = (
            "literature review will search pubmed for relevant papers and analyze them"
        )
    else:
        lit_review_description = "literature review is not available (no pubmed access)"

    return load_prompt_with_schema(
        "supervisor",
        {
            "research_goal": research_goal,
            "preferences": preferences or "None provided",
            "attributes": ", ".join(attributes) if attributes else "None provided",
            "constraints": (
                "\n".join(f"- {c}" for c in constraints) if constraints else "None provided"
            ),
            "user_hypotheses": (
                "\n".join(f"- {h}" for h in user_hypotheses) if user_hypotheses else "None provided"
            ),
            "user_literature": (
                "\n".join(f"- {lit}" for lit in user_literature)
                if user_literature
                else "None provided"
            ),
            "initial_hypotheses_count": initial_hypotheses_count or "not specified",
            "max_iterations": max_iterations or "not specified",
            "evolution_max_count": evolution_max_count or "not specified",
            "literature_review_description": lit_review_description,
        },
    )


# Helper functions to format supervisor guidance for different contexts
def _format_supervisor_guidance_for_review(supervisor_guidance: Dict[str, Any] | None) -> str:
    """Format supervisor guidance for review prompts."""
    if not supervisor_guidance or not isinstance(supervisor_guidance, dict):
        return ""

    sections = []
    workflow_plan = supervisor_guidance.get("workflow_plan", {})
    review_phase = workflow_plan.get("review_phase", {})

    if review_phase:
        sections.append("## Supervisor Guidance for Review\n")
        if review_phase.get("critical_criteria"):
            criteria = review_phase["critical_criteria"]
            if isinstance(criteria, list):
                criteria = ", ".join(criteria)
            sections.append(f"**Critical Criteria to Emphasize:** {criteria}\n")
        if review_phase.get("review_depth"):
            sections.append(f"**Review Depth Required:** {review_phase['review_depth']}\n")

    return "".join(sections) if sections else ""


def _format_supervisor_guidance_for_ranking(supervisor_guidance: Dict[str, Any] | None) -> str:
    """Format supervisor guidance for ranking prompts."""
    if not supervisor_guidance or not isinstance(supervisor_guidance, dict):
        return ""

    sections = []
    goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
    key_areas = goal_analysis.get("key_areas", [])

    if key_areas:
        sections.append("## Supervisor Guidance\n")
        sections.append("**Key Research Areas to Consider:**\n")
        for area in key_areas:
            sections.append(f"- {area}\n")
        sections.append(
            "\nWhen comparing hypotheses, prioritize those that better address these key areas.\n"
        )

    return "".join(sections) if sections else ""


def _format_supervisor_guidance_for_proximity(supervisor_guidance: Dict[str, Any] | None) -> str:
    """Format supervisor guidance for proximity prompts."""
    if not supervisor_guidance or not isinstance(supervisor_guidance, dict):
        return ""

    sections = []
    goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
    key_areas = goal_analysis.get("key_areas", [])

    if key_areas:
        sections.append("## Supervisor Guidance\n")
        sections.append("**Key Research Areas:**\n")
        for area in key_areas:
            sections.append(f"- {area}\n")
        sections.append(
            "\nWhen assessing similarity, consider whether hypotheses explore different aspects of these key areas. Hypotheses that address the same area with similar approaches should be flagged as duplicates.\n"
        )

    return "".join(sections) if sections else ""


def _format_meta_review_context(meta_review: Dict[str, Any] | None) -> str:
    """Format meta-review insights for review prompts (when re-reviewing evolved hypotheses)."""
    if not meta_review or not isinstance(meta_review, dict):
        return ""

    sections = []
    sections.append("## Meta-Review Context\n")
    sections.append(
        "The following insights were synthesized from previous reviews of all hypotheses:\n\n"
    )

    common_strengths = meta_review.get("common_strengths", [])
    if common_strengths:
        sections.append("**Common Strengths Across Hypotheses:**\n")
        for strength in common_strengths:
            sections.append(f"- {strength}\n")
        sections.append("\n")

    common_weaknesses = meta_review.get("common_weaknesses", [])
    if common_weaknesses:
        sections.append("**Common Weaknesses to Watch For:**\n")
        for weakness in common_weaknesses:
            sections.append(f"- {weakness}\n")
        sections.append("\n")

    strategic_recommendations = meta_review.get("strategic_recommendations", [])
    if strategic_recommendations:
        sections.append("**Strategic Recommendations:**\n")
        for rec in strategic_recommendations:
            if isinstance(rec, dict):
                rec_text = rec.get("recommendation", str(rec))
            else:
                rec_text = str(rec)
            sections.append(f"- {rec_text}\n")
        sections.append("\n")

    sections.append("Use these insights to provide more informed and consistent reviews.\n")

    return "".join(sections) if sections else ""


def _format_review_context(review_a: Dict[str, Any] | None, review_b: Dict[str, Any] | None) -> str:
    """Format review scores for ranking prompts."""
    if not review_a and not review_b:
        return ""

    sections = []
    sections.append("## Review Scores Context\n")
    sections.append("The following review scores are available to inform your comparison:\n\n")

    if review_a:
        sections.append("**Hypothesis A Review Scores:**\n")
        if isinstance(review_a, dict):
            if "scores" in review_a:
                for criterion, score in review_a["scores"].items():
                    sections.append(f"- {criterion}: {score}\n")
            if "overall_score" in review_a:
                sections.append(f"- Overall Score: {review_a['overall_score']}\n")
        sections.append("\n")

    if review_b:
        sections.append("**Hypothesis B Review Scores:**\n")
        if isinstance(review_b, dict):
            if "scores" in review_b:
                for criterion, score in review_b["scores"].items():
                    sections.append(f"- {criterion}: {score}\n")
            if "overall_score" in review_b:
                sections.append(f"- Overall Score: {review_b['overall_score']}\n")
        sections.append("\n")

    sections.append(
        "Consider these scores, but make your judgment based on comprehensive comparison, not just scores.\n"
    )

    return "".join(sections) if sections else ""


def _format_supervisor_guidance_for_meta_review(supervisor_guidance: Dict[str, Any] | None) -> str:
    """Format supervisor guidance for meta-review prompts."""
    if not supervisor_guidance or not isinstance(supervisor_guidance, dict):
        return ""

    sections = []
    sections.append("## Supervisor Guidance\n")

    # Add key research areas
    goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
    key_areas = goal_analysis.get("key_areas", [])
    if key_areas:
        sections.append("**Key Research Areas:**\n")
        for area in key_areas:
            sections.append(f"- {area}\n")
        sections.append("\n")

    # Add evolution phase guidance
    workflow_plan = supervisor_guidance.get("workflow_plan", {})
    evolution_phase = workflow_plan.get("evolution_phase", {})
    if evolution_phase:
        sections.append("**Evolution Phase Guidance:**\n")
        if evolution_phase.get("refinement_priorities"):
            priorities = evolution_phase["refinement_priorities"]
            if isinstance(priorities, list):
                priorities = ", ".join(priorities)
            sections.append(f"- Refinement Priorities: {priorities}\n")
        if evolution_phase.get("iteration_strategy"):
            sections.append(f"- Iteration Strategy: {evolution_phase['iteration_strategy']}\n")
        sections.append("\n")

    sections.append(
        "Use this guidance to ensure your meta-review synthesis aligns with the research plan and evolution strategy.\n"
    )

    return "".join(sections) if sections else ""


def get_reflection_prompt(
    articles_with_reasoning: str, hypothesis_text: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Get the reflection observations prompt and schema."""
    return load_prompt_with_schema(
        "reflection_observations",
        {"articles_with_reasoning": articles_with_reasoning, "hypothesis": hypothesis_text},
    )


def get_literature_review_query_generation_pubmed_prompt(
    research_goal: str,
    preferences: str | None = None,
    attributes: list[str] | None = None,
    user_literature: list[str] | None = None,
    user_hypotheses: list[str] | None = None,
) -> str:
    """Get the PubMed query generation prompt."""
    return load_prompt(
        "literature_review_query_generation_pubmed",
        {
            "research_goal": research_goal,
            "preferences": preferences if preferences else "None provided",
            "attributes": ", ".join(attributes) if attributes else "None provided",
            "user_literature": (
                "\n".join(f"- {lit}" for lit in user_literature)
                if user_literature
                else "None provided"
            ),
            "user_hypotheses": (
                "\n".join(f"- {hyp}" for hyp in user_hypotheses)
                if user_hypotheses
                else "None provided"
            ),
        },
    )


def get_literature_review_paper_analysis_prompt(
    research_goal: str, title: str, authors: list[str], year: int | None, fulltext: str
) -> str:
    """Get the prompt for analyzing a single paper."""
    authors_str = ", ".join(authors) if authors else "Unknown"
    year_str = str(year) if year else "Unknown"

    return load_prompt(
        "literature_review_paper_analysis",
        {
            "research_goal": research_goal,
            "title": title,
            "authors": authors_str,
            "year": year_str,
            "fulltext": fulltext,
        },
    )


def get_literature_review_synthesis_prompt(
    research_goal: str, paper_analyses: list[Dict[str, Any]]
) -> str:
    """Get the prompt for synthesizing paper analyses."""
    # format paper analyses as structured text
    analyses_text = []
    for i, analysis_data in enumerate(paper_analyses, 1):
        metadata = analysis_data.get("metadata", {})
        analysis = analysis_data.get("analysis", {})

        paper_section = f"""### paper {i}: {metadata.get('title', 'Unknown')}
**authors:** {', '.join(metadata.get('authors', ['Unknown']))}
**year:** {metadata.get('year', 'Unknown')}

**key findings:** {analysis.get('key_findings', 'N/A')}

**gaps identified:** {analysis.get('gaps_identified', 'N/A')}

**future work suggested:** {analysis.get('future_work', 'N/A')}

**methodology limitations:** {analysis.get('methodology_limitations', 'N/A')}

**unexplored areas:** {analysis.get('unexplored_areas', 'N/A')}

**relevance:** {analysis.get('relevance', 'N/A')}
"""
        analyses_text.append(paper_section)

    return load_prompt(
        "literature_review_synthesis",
        {"research_goal": research_goal, "paper_analyses": "\n\n".join(analyses_text)},
    )


def get_hypothesis_novelty_analysis_prompt(
    hypothesis_text: str, title: str, authors: list[str], year: int | None, fulltext: str
) -> str:
    """Get the prompt for analyzing a paper for hypothesis novelty."""
    authors_str = ", ".join(authors) if authors else "Unknown"
    year_str = str(year) if year else "Unknown"

    return load_prompt(
        "hypothesis_novelty_analysis",
        {
            "hypothesis_text": hypothesis_text,
            "title": title,
            "authors": authors_str,
            "year": year_str,
            "fulltext": fulltext,
        },
    )


def get_hypothesis_validation_synthesis_prompt(
    research_goal: str,
    hypotheses_with_analyses: list[Dict[str, Any]],
    articles: List[Any] | None = None,
) -> str:
    """
    Get the prompt for validation synthesis based on novelty analyses.

    Args:
        research_goal: The research goal
        hypotheses_with_analyses: List of draft hypotheses with novelty analyses
        articles: Optional list of Article objects for citation metadata

    Returns:
        Formatted prompt string
    """
    # format hypotheses with their novelty analyses
    hypotheses_text = []
    for i, hyp_data in enumerate(hypotheses_with_analyses, 1):
        draft = hyp_data.get("draft", {})
        analyses = hyp_data.get("novelty_analyses", [])

        hyp_section = f"""### draft hypothesis {i}
**text:** {draft.get('text', 'Unknown')}
**gap reasoning:** {draft.get('gap_reasoning', 'N/A')}
**literature sources:** {draft.get('literature_sources', 'N/A')}

**novelty analyses ({len(analyses)} papers examined):**
"""

        for j, analysis_data in enumerate(analyses, 1):
            paper_meta = analysis_data.get("paper_metadata", {})
            analysis = analysis_data.get("analysis", {})

            paper_analysis = f"""
**paper {j}:** {paper_meta.get('title', 'Unknown')} ({paper_meta.get('year', 'N/A')})
- methods used: {analysis.get('methods_used', 'N/A')}
- populations studied: {analysis.get('populations_studied', 'N/A')}
- mechanisms investigated: {analysis.get('mechanisms_investigated', 'N/A')}
- key findings: {analysis.get('key_findings', 'N/A')}
- stated limitations: {analysis.get('stated_limitations', 'N/A')}
- future work suggested: {analysis.get('future_work_suggested', 'N/A')}
- **novelty assessment: {analysis.get('novelty_assessment', 'N/A')}**
- overlap explanation: {analysis.get('overlap_explanation', 'N/A')}
"""
            hyp_section += paper_analysis

        hypotheses_text.append(hyp_section)

    return load_prompt(
        "hypothesis_validation_synthesis",
        {
            "research_goal": research_goal,
            "hypotheses_with_analyses": "\n\n".join(hypotheses_text),
            "articles_metadata": format_articles_metadata(articles or []),
        },
    )


def get_debate_generation_prompt(
    research_goal: str,
    hypotheses_count: int,
    transcript: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    preferences: str | None = None,
    attributes: str | None = None,
    is_final_turn: bool = False,
    articles_with_reasoning: str | None = None,
    articles: List[Any] | None = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Get the debate-based hypothesis generation prompt.

    This uses a multi-turn debate strategy where experts discuss and refine hypotheses.
    The transcript accumulates over multiple turns until final hypotheses are generated.

    Args:
        research_goal: The research goal
        hypotheses_count: Number of hypotheses to generate
        transcript: Accumulated conversation transcript from previous turns
        supervisor_guidance: Optional guidance from supervisor
        preferences: Criteria for strong hypotheses
        attributes: Key attributes to prioritize
        is_final_turn: Whether this is the final turn (outputs JSON schema)
        articles_with_reasoning: Optional literature review synthesis for context
        articles: Optional list of Article objects for citation metadata

    Returns:
        Tuple of (formatted prompt string, JSON schema dict or None)
    """
    variables = {
        "goal": research_goal,
        "hypotheses_count": hypotheses_count,
        "transcript": transcript or "",
        "preferences": preferences
        or "Novel, testable, scientifically sound, specific, and diverse hypotheses",
        "attributes": (
            ", ".join(attributes)
            if attributes and isinstance(attributes, list)
            else (attributes or "testable and falsifiable")
        ),
    }

    # add literature review if provided
    if articles_with_reasoning:
        variables["articles_with_reasoning"] = articles_with_reasoning

    # add article metadata for citations
    variables["articles_metadata"] = format_articles_metadata(articles or [])

    # Format supervisor guidance if available
    if supervisor_guidance and isinstance(supervisor_guidance, dict):
        guidance_sections = []
        has_content = False

        goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
        key_areas = goal_analysis.get("key_areas", [])
        if key_areas:
            if not has_content:
                guidance_sections.append("Key research areas to consider:\n")
                has_content = True
            for area in key_areas:
                guidance_sections.append(f"- {area}\n")

        workflow_plan = supervisor_guidance.get("workflow_plan", {})
        generation_phase = workflow_plan.get("generation_phase", {})
        if generation_phase:
            if not has_content:
                guidance_sections.append("Generation guidance:\n")
                has_content = True
            if generation_phase.get("focus_areas"):
                focus_areas = generation_phase["focus_areas"]
                if isinstance(focus_areas, list):
                    focus_areas = ", ".join(focus_areas)
                guidance_sections.append(f"Focus on: {focus_areas}\n")

        variables["supervisor_guidance"] = "".join(guidance_sections) if has_content else ""
    else:
        variables["supervisor_guidance"] = ""

    # determine which prompt to use based on literature availability
    prompt_name = (
        "generation_debate_and_literature" if articles_with_reasoning else "generation_after_debate"
    )

    # if final turn, append instruction to output JSON and use schema
    if is_final_turn:
        prompt, schema = load_prompt_with_schema(prompt_name, variables)

        # append JSON output instructions for final turn
        final_instructions = """

## FINAL TURN - OUTPUT FORMAT

This is the final turn of the debate. Based on the discussion above, output your finalized hypothesis in JSON format with all four required components:

### 1. hypothesis (required)
Dense technical description following "We want to develop [X] to enable [Y]" format (2-3 sentences).
- Include specific technical details: algorithms, mechanisms, mathematical formulations
- Be precise about what will be developed and the technical approach

Example: "We want to develop a 'Dynamic Velocity Sentinel'—which monitors the rate of change in latent activation directions across early-to-mid layers rather than static depths—to enable anticipatory gating that triggers only when precursor signals cross a 'point of no return' for danger features."

### 2. explanation (required)
Clear explanation for technical audiences in layman terms (4-6 sentences).
- Core problem being addressed
- Why key mechanisms work
- How components interact
- Practical advantages

Example: "This approach addresses the computational bottleneck by focusing on early layers where precursor signals first emerge. Rather than analyzing static magnitudes, the technique tracks velocity—the rate of change—which provides earlier detection of trajectories toward dangerous outputs. The system employs autoencoders to identify danger features, with dynamic gating that triggers only when trajectories cross a learned threshold."

### 3. literature_grounding (required)
Explicit grounding with proper citations (2-4 sentences).
- Use (Author et al., year) format consistently
- Connect specific findings from literature to hypothesis
- If no literature available, state: "This hypothesis is formulated without access to a literature review."

Example: "This approach builds on recent work in autoencoder analysis (Templeton et al., 2024) and circuit tracing (Conmy et al., 2023). The velocity monitoring concept addresses a gap in current methods that focus on static analysis (Marks et al., 2024)."

### 4. experiment (required)
Concrete experiment design with models, datasets, methodology, metrics, and validation (4-6 sentences).

Example format: "Objective: Demonstrate that velocity monitoring achieves comparable detection with reduced cost. Models: GPT-2 Medium, pre-trained SAE layers 1-6. Datasets: AdvBench harmful prompts (500 examples), HH-RLHF benign prompts (1000 examples). Methodology: (1) Implement velocity tracking, (2) Train threshold detector, (3) Compare against baseline. Metrics: Detection accuracy, timing, false positive rate, computational overhead. Validation: Success requires >90% detection, <5% false positives, >50% cost reduction."

---

Output exactly 1 hypothesis as valid JSON:
{
  "hypotheses": [
    {
      "hypothesis": "...",
      "explanation": "...",
      "literature_grounding": "...",
      "experiment": "..."
    }
  ]
}

IMPORTANT: Use plain text with standard punctuation (no LaTeX, no decorative Unicode).
"""
        prompt = prompt + final_instructions
        return prompt, schema
    else:
        # non-final turns: no schema, just conversational
        prompt = load_prompt(prompt_name, variables)
        return prompt, None


# formatting helpers for generate node


def format_preferences(preferences: str | None) -> str:
    """format user preferences for prompts"""
    if preferences:
        return preferences
    return "Focus on novelty, testability, and potential impact."


def format_attributes(attributes: List[str] | None) -> str:
    """format user attributes for prompts"""
    if attributes:
        return "\n".join(f"- {attr}" for attr in attributes)
    return "- Novel\n- Testable\n- Impactful"


def format_user_hypotheses(user_hypotheses: List[str] | None) -> str:
    """format user-provided starting hypotheses for prompts"""
    if user_hypotheses:
        return "\n".join(f"- {hyp}" for hyp in user_hypotheses)
    return "No user-provided starting hypotheses."


def format_supervisor_guidance_for_generation(supervisor_guidance: Dict[str, Any] | None) -> str:
    """format supervisor guidance for generation prompts with research strategy section"""
    if not supervisor_guidance:
        return ""

    research_plan = supervisor_guidance.get("research_plan", "")
    if research_plan and research_plan.strip():
        return f"""
## Research Strategy

{research_plan}
"""
    return ""


def condense_literature_summary(articles_with_reasoning: str | None) -> str:
    """
    Condense full literature review summary to concise overview

    Agent will read papers directly with tools, so keep brief (~15-20 lines)
    Extracts 2-3 key sentences covering main themes and gaps
    """
    if not articles_with_reasoning:
        return "No pre-curated literature review available."

    # simple strategy: take first ~500 chars (usually covers main findings)
    # plus extract any "gap" or "limitation" mentions
    text = articles_with_reasoning.strip()

    # find main content sections (skip headers)
    lines = [line for line in text.split("\n") if line.strip() and not line.startswith("#")]

    # take first 2-3 substantive lines for themes
    theme_lines = []
    for line in lines[:10]:  # look in first 10 lines
        if len(line) > 50:  # substantive line
            theme_lines.append(line.strip())
            if len(theme_lines) >= 2:
                break

    # look for gap/limitation mentions
    gap_lines = []
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["gap", "limitation", "unsolved", "need for", "lack of"]):
            if len(line) > 50:  # substantive
                gap_lines.append(line.strip())
                if len(gap_lines) >= 2:
                    break

    parts = []
    if theme_lines:
        # take first 300 chars of themes
        themes_text = " ".join(theme_lines)[:300]
        parts.append(f"**Key Themes:** {themes_text}...")

    if gap_lines:
        # take first 250 chars of gaps
        gaps_text = " ".join(gap_lines)[:250]
        parts.append(f"**Identified Gaps:** {gaps_text}...")

    # fallback: just take first 400 chars
    if not parts:
        return (
            text[:400] + "...\n\n(See papers below for details. Use tools to read papers directly.)"
        )

    result = "\n\n".join(parts)
    result += (
        "\n\n(Brief summary - use tools to examine papers directly for comprehensive details.)"
    )
    return result


def format_articles_metadata(articles: List[Any]) -> str:
    """
    format analyzed articles with metadata for tool-based generation prompts

    returns structured list of articles with titles, authors, year, citations, pdf availability
    only includes articles with used_in_analysis=True
    """
    if not articles:
        return ""

    used_articles = [art for art in articles if art.used_in_analysis]
    if not used_articles:
        return ""

    articles_list_text = "\n\n".join(
        [
            f"**{i+1}. {art.title}**\n"
            f"   - Authors: {', '.join(art.authors[:3])}{' et al.' if len(art.authors) > 3 else ''}\n"
            f"   - Year: {art.year or 'Unknown'}\n"
            f"   - Citations: {art.citations}\n"
            f"   - PDF: {'Available - ' + art.pdf_links[0] if art.pdf_links else 'No PDF found (abstract only)'}\n"
            f"   - URL: {art.url}"
            for i, art in enumerate(used_articles)
        ]
    )

    return f"""
### Papers Analyzed in Literature Review

These {len(used_articles)} papers were ranked highest and analyzed. Some may have had accessibility issues (abstracts only, paywalls, captchas).
You can use tools to:
- Try accessing PDFs that weren't available initially
- Query specific papers for detailed information
- Search for alternative papers if these have issues

{articles_list_text}
"""


def build_tool_instructions(
    tool_ids: List[str],
    tool_registry: Optional[Any] = None,
) -> str:
    """
    Build dynamic tool instructions section from tool registry.

    Args:
        tool_ids: List of tool IDs to include in instructions
        tool_registry: ToolRegistry instance with tool configurations

    Returns:
        Formatted markdown section describing available tools
    """
    # if no registry provided, try to get the global one
    if tool_registry is None:
        try:
            from .config import get_tool_registry

            tool_registry = get_tool_registry()
            # if no tool_ids provided, get them from draft workflow
            if not tool_ids:
                tool_ids = tool_registry.get_tools_for_workflow("draft_generation")
        except Exception:
            pass

    if not tool_registry or not tool_ids:
        # minimal fallback when no config available
        return "No tool configuration available. Literature tools may not be accessible."

    sections = []

    for tool_id in tool_ids:
        tool_config = tool_registry.get_tool(tool_id)
        if not tool_config or not tool_config.enabled:
            continue

        # add tool entry
        sections.append(f"- `{tool_config.mcp_tool_name}`: {tool_config.description}")

        # add prompt snippet if available
        if tool_config.prompt_snippet:
            # indent the snippet
            snippet_lines = tool_config.prompt_snippet.strip().split("\n")
            for line in snippet_lines:
                sections.append(f"  {line}")

        sections.append("")  # blank line between tools

    if not sections:
        return "No tools available."

    return "\n".join(sections).strip()


def get_draft_prompt_with_tools(
    research_goal: str,
    hypotheses_count: int,
    supervisor_guidance: Dict[str, Any] | None = None,
    articles: List[Any] | None = None,
    articles_with_reasoning: str | None = None,
    preferences: str | None = None,
    attributes: List[str] | None = None,
    user_hypotheses: List[str] | None = None,
    instructions: str | None = None,
    max_iterations: int = 8,
    tool_registry: Optional[Any] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Get prompt for Phase 1: drafting hypotheses with tools.

    Uses generation_draft_with_tools.md template.
    Focuses on reading papers and identifying gaps.
    Includes lit review summary as context (not instructions).

    Args:
        research_goal: The research goal
        hypotheses_count: Number of hypotheses to draft
        supervisor_guidance: Optional guidance from supervisor
        articles: List of Article objects from literature review
        articles_with_reasoning: Literature review synthesis
        preferences: Criteria for strong hypotheses
        attributes: Key attributes to prioritize
        user_hypotheses: User-provided starting hypotheses
        instructions: Custom instructions
        max_iterations: Max tool iterations for the agent
        tool_registry: Optional ToolRegistry for dynamic tool instructions
    """
    # get tool IDs for draft generation workflow
    tool_ids = []
    if tool_registry:
        tool_ids = tool_registry.get_tools_for_workflow("draft_generation")

    # build dynamic tool instructions
    tool_instructions = build_tool_instructions(tool_ids, tool_registry)

    variables = {
        "goal": research_goal,
        "hypotheses_count": hypotheses_count,
        "preferences": format_preferences(preferences),
        "attributes": format_attributes(attributes),
        "user_hypotheses": format_user_hypotheses(user_hypotheses),
        "supervisor_guidance": format_supervisor_guidance_for_generation(supervisor_guidance),
        "articles_with_reasoning": articles_with_reasoning
        or "no literature review summary available - examine papers below directly.",
        "articles_metadata": format_articles_metadata(articles or []),
        "max_iterations": max_iterations,
        "instructions": instructions
        or "Focus on creative ideation - draft diverse hypotheses based on literature gaps.",
        "tool_instructions": tool_instructions,
    }

    return load_prompt_with_schema("generation_draft_with_tools", variables)
