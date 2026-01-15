"""
Phase 1: Draft hypotheses by reading papers and identifying gaps.

This is the first phase of tool-based generation. The agent reads pre-curated
papers using tools and drafts initial hypothesis ideas based on identified gaps.
"""

import hashlib
import logging
import os
from typing import Any, Dict, List

from ....constants import (
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    get_draft_max_iterations,
)
from ....llm import call_llm_with_tools, attempt_json_repair
from ....prompts import get_draft_prompt_with_tools
from ....state import WorkflowState
from ....tools.literature import literature_tools
from ....tools.provider import HybridToolProvider

logger = logging.getLogger(__name__)


async def draft_hypotheses(
    state: WorkflowState, count: int, mcp_client: Any
) -> List[Dict[str, str]]:
    """
    phase 1: draft hypotheses by searching pubmed for metadata

    uses tools for searching biomedical literature:
    - search_pubmed (search pubmed and get paper metadata: title, abstract, authors, DOI)

    note: fulltext download analysis deferred to validate phase

    args:
        state: current workflow state
        count: number of hypotheses to draft
        mcp_client: MCP client for tool access

    returns:
        list of draft dicts with text, gap_reasoning, literature_sources
    """
    logger.info(f"Phase 1: Drafting {count} hypotheses by examining literature")

    # get state variables
    supervisor_guidance = state.get("supervisor_guidance", {})
    articles_with_reasoning = state.get("articles_with_reasoning")
    preferences = state.get("preferences")
    attributes = state.get("attributes")
    user_hypotheses = state.get("user_inputs", {}).get("starting_hypotheses")
    articles = state.get("articles", [])

    # create shared slug for corpus (reuse lit review slug for warm start)
    research_goal = state["research_goal"]
    shared_slug = "research_" + hashlib.md5(research_goal.encode()).hexdigest()[:8]
    logger.info(f"Using shared corpus slug: {shared_slug}")

    # store slug in state for validation phase to reuse
    state["generation_corpus_slug"] = shared_slug

    # log lit review context
    if articles_with_reasoning:
        logger.info("Including lit review summary as context for drafting")
        logger.info(
            f"Warm start: corpus already populated with {len(articles)} papers from literature review"
        )
    else:
        logger.warning("No lit review summary available - agent will examine papers directly")

    # initialize hybrid tool provider with draft-specific whitelist
    provider = HybridToolProvider(mcp_client=mcp_client, python_registry=literature_tools)

    # draft whitelist: pubmed metadata search only (no fulltext download)
    # validate phase will download fulltexts for novelty checking
    mcp_whitelist = ["search_pubmed"]
    python_whitelist = []

    tools_dict, openai_tools = provider.get_tools(
        mcp_whitelist=mcp_whitelist, python_whitelist=python_whitelist
    )

    logger.info(
        f"Initialized draft provider with {len(tools_dict)} tools (pubmed metadata search only)"
    )

    # calculate dynamic iteration budget based on hypotheses count
    max_iterations = get_draft_max_iterations(count)
    logger.info(f"Draft budget: {max_iterations} iterations for {count} hypotheses")

    # build draft prompt with lit review summary as context
    prompt, schema = get_draft_prompt_with_tools(
        research_goal=state["research_goal"],
        hypotheses_count=count,
        supervisor_guidance=supervisor_guidance,
        articles=articles,
        articles_with_reasoning=articles_with_reasoning,
        preferences=preferences,
        attributes=attributes,
        user_hypotheses=user_hypotheses,
        max_iterations=max_iterations,
    )

    # write prompt to disk
    try:
        run_id = state.get("run_id", "unknown")
        prompts_output_dir = os.path.join(".coscientist_prompts", run_id)
        os.makedirs(prompts_output_dir, exist_ok=True)
        prompt_output_path = os.path.join(prompts_output_dir, "generate_draft_with_tools.txt")
        with open(prompt_output_path, "w") as f:
            f.write(prompt)
        logger.debug(f"wrote draft prompt to: {prompt_output_path}")
    except Exception as e:
        logger.warning(f"Failed to write draft prompt to disk: {e}")

    # track searches in draft phase
    searches_performed_draft = []

    # track tool calls
    tool_call_count = {"pubmed_search": 0}

    # create tracked executor for draft phase
    async def draft_tracked_executor(tool_call):
        """track searches for draft phase"""
        tool_name = tool_call.function.name

        # track pubmed searches (but don't limit - let agent decide)
        if tool_name == "search_pubmed":
            tool_call_count["pubmed_search"] += 1
            searches_performed_draft.append(tool_name)
            logger.info(
                f"Draft: PubMed search #{tool_call_count['pubmed_search']} (metadata only, no fulltext)"
            )

        # execute tool
        return await provider.execute_tool_call(tool_call)

    # call LLM with tools for drafting
    # scale token budget based on hypotheses count (~200 tokens per hypothesis)
    draft_max_tokens = min(EXTENDED_MAX_TOKENS + (count * 200), 16000)
    logger.info(f"Calling draft agent: {max_iterations} iterations, {draft_max_tokens} max tokens")

    try:
        final_response, messages = await call_llm_with_tools(
            prompt=prompt,
            model_name=state["model_name"],
            tools=openai_tools,
            tool_executor=draft_tracked_executor,
            max_tokens=draft_max_tokens,
            temperature=HIGH_TEMPERATURE,
            max_iterations=max_iterations,
        )
    except Exception as e:
        logger.error(f"Draft phase failed: {e}")
        raise

    logger.info(
        f"Draft phase complete: {tool_call_count['pubmed_search']} PubMed searches (metadata only, fulltext deferred to validate)"
    )

    # parse JSON response (strip markdown if present, then use repair logic)
    response_text = final_response.strip()

    # handle markdown code blocks (case-insensitive)
    response_lower = response_text.lower()
    if "```json" in response_lower:
        # find ```json (case-insensitive)
        start_idx = response_lower.find("```json")
        json_start = start_idx + 7  # length of "```json"
        # find closing ``` after the opening
        json_end = response_text.find("```", json_start)
        if json_end == -1:
            # no closing ``` found, use rest of text
            response_text = response_text[json_start:].strip()
        else:
            response_text = response_text[json_start:json_end].strip()
    elif "```" in response_text:
        # plain code block without "json"
        json_start = response_text.find("```") + 3
        json_end = response_text.find("```", json_start)
        if json_end == -1:
            response_text = response_text[json_start:].strip()
        else:
            response_text = response_text[json_start:json_end].strip()

    # additional cleanup - remove leading/trailing whitespace and newlines
    response_text = response_text.strip().strip("\n").strip()

    # use attempt_json_repair for robust parsing
    response_data, was_repaired = attempt_json_repair(response_text, allow_major_repairs=True)

    if response_data is None:
        logger.error("Failed to parse draft JSON response after all repair attempts")
        logger.error(f"Response: {final_response[:500]}...")
        raise ValueError("Draft phase returned invalid JSON that could not be repaired")

    if was_repaired:
        logger.warning("Draft JSON response required major repairs (possible truncation)")

    drafts = response_data.get("drafts", [])
    logger.info(f"Parsed {len(drafts)} draft hypotheses")
    return drafts
