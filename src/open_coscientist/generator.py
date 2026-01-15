"""
Main HypothesisGenerator class.

Provides an interface inspired by the original AI-CoScientist integration,
but uses LangGraph under the hood.
"""

import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Literal, Optional, Tuple, Union, overload

from langgraph.graph import END, StateGraph

from .constants import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_INITIAL_HYPOTHESES_COUNT,
    DEFAULT_EVOLUTION_MAX_COUNT,
)
from .models import ExecutionMetrics
from .nodes.generate import generate_node
from .nodes.literature_review import literature_review_node
from .nodes.reflection import reflection_node
from .nodes.review import review_node
from .nodes.ranking import ranking_node
from .nodes.meta_review import meta_review_node
from .nodes.evolve import evolve_node
from .nodes.proximity import proximity_node
from .nodes.supervisor import supervisor_node
from .state import WorkflowState

logger = logging.getLogger(__name__)


class HypothesisGenerator:
    """
    Async wrapper for hypothesis generation using LangGraph.

    Example:
        >>> generator = HypothesisGenerator(
        ...     model_name="gemini/gemini-2.5-flash",
        ...     max_iterations=1,
        ...     initial_hypotheses_count=5,
        ...     evolution_max_count=3
        ... )
        >>> result = await generator.generate_hypotheses(
        ...     research_goal="Cure cancer",
        ...     progress_callback=my_callback
        ... )
    """

    def __init__(
        self,
        model_name: str = "gemini/gemini-2.5-flash",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        initial_hypotheses_count: int = DEFAULT_INITIAL_HYPOTHESES_COUNT,
        evolution_max_count: int = DEFAULT_EVOLUTION_MAX_COUNT,
        enable_cache: Optional[bool] = None,
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize the hypothesis generator.

        Args:
            model_name: LLM model to use (litellm format)
            max_iterations: Number of refinement iterations
            initial_hypotheses_count: Number of initial hypotheses
            evolution_max_count: Number of top hypotheses to evolve
            enable_cache: Enable/disable LLM response caching (None = use env var)
            cache_dir: Directory for cache files (None = use default)
        """
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.initial_hypotheses_count = initial_hypotheses_count
        self.evolution_max_count = evolution_max_count

        # Configure cache if specified
        if enable_cache is not None:
            import os
            os.environ["COSCIENTIST_CACHE_ENABLED"] = "true" if enable_cache else "false"
        if cache_dir is not None:
            import os
            os.environ["COSCIENTIST_CACHE_DIR"] = cache_dir

        # Build the graph (lazy - only once)
        self._graph = None

        # Cache availability checks per instance (lazy init on first generate call)
        self._mcp_available: Optional[bool] = None
        self._pubmed_available: Optional[bool] = None

    def _build_graph(self, enable_literature_review_node: bool = True) -> StateGraph:
        """
        Build the LangGraph workflow.

        Complete workflow:
        1. SUPERVISOR → creates research plan
        2. LITERATURE_REVIEW → search and analyze literature (optional, if MCP available)
        3. GENERATE → initial hypotheses
        4. REFLECTION → analyze hypotheses against literature (skipped if no lit review)
        5. REVIEW → parallel peer reviews
        6. RANKING → sort by score, then run Elo tournaments
        7. ITERATIONS (if max_iterations > 0):
           - META_REVIEW → synthesize insights
           - EVOLVE → refine top-k hypotheses
           - REVIEW → re-review evolved hypotheses
           - RANKING → update Elo ratings
           - PROXIMITY → deduplicate similar hypotheses
           - Loop back or END
        8. END → return top hypotheses

        Args:
            enable_literature_review_node: Whether to include literature review node (requires MCP server)
        """
        workflow = StateGraph(WorkflowState)

        # Add all nodes
        workflow.add_node("supervisor", supervisor_node)
        workflow.add_node("generate", generate_node)
        workflow.add_node("review", review_node)
        workflow.add_node("ranking", ranking_node)
        workflow.add_node("meta_review", meta_review_node)
        workflow.add_node("evolve", evolve_node)
        workflow.add_node("proximity", proximity_node)

        # Conditionally add literature review and reflection nodes
        if enable_literature_review_node:
            workflow.add_node("literature_review", literature_review_node)
            workflow.add_node("reflection", reflection_node)

        # Initial flow - conditional based on literature review availability
        workflow.set_entry_point("supervisor")

        if enable_literature_review_node:
            # Full flow: supervisor → literature_review → generate → reflection → review → ranking
            workflow.add_edge("supervisor", "literature_review")
            workflow.add_edge("literature_review", "generate")
            workflow.add_edge("generate", "reflection")
            workflow.add_edge("reflection", "review")
        else:
            # Simplified flow: supervisor → generate → review → ranking
            workflow.add_edge("supervisor", "generate")
            workflow.add_edge("generate", "review")

        workflow.add_edge("review", "ranking")

        # Iteration cycle: meta_review → evolve → review → ranking → proximity
        workflow.add_edge("meta_review", "evolve")
        workflow.add_edge("evolve", "review")  # Re-review evolved hypotheses
        # Note: review → ranking already defined above

        # Conditional: after tournament, decide next step
        def after_ranking(state: WorkflowState) -> str:
            """Decide what to do after ranking based on workflow state."""
            current_iteration = state.get("current_iteration", 0)
            max_iterations = state.get("max_iterations", 0)
            # Check if we've already run meta_review (indicates we're in iteration cycle)
            has_meta_review = bool(state.get("meta_review", {}))

            if not has_meta_review:
                # First ranking - check if we should start iterating
                if current_iteration < max_iterations:
                    logger.info(f"Starting iteration {current_iteration + 1}/{max_iterations}")
                    return "iterate"
                else:
                    logger.info("No iterations needed, ending workflow")
                    return "end"
            else:
                # We're in an iteration cycle - go through proximity for deduplication
                logger.info("Going through proximity check")
                return "proximity"

        workflow.add_conditional_edges(
            "ranking",
            after_ranking,
            {
                "iterate": "meta_review",
                "proximity": "proximity",
                "end": END
            }
        )

        # After proximity, check if we should continue iterating
        def after_proximity(state: WorkflowState) -> str:
            """Check if should continue after proximity deduplication."""
            # Note: proximity node increments current_iteration
            current_iteration = state.get("current_iteration", 0)
            max_iterations = state.get("max_iterations", 0)

            if current_iteration < max_iterations:
                logger.info(f"Continuing to iteration {current_iteration + 1}/{max_iterations}")
                return "iterate"
            else:
                logger.info("All iterations complete after deduplication")
                return "end"

        workflow.add_conditional_edges(
            "proximity",
            after_proximity,
            {
                "iterate": "meta_review",
                "end": END
            }
        )

        return workflow.compile()

    async def _prepare_generation(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Tuple[WorkflowState, float, str]:
        """
        Prepare generation by setting up state, checking MCP availability, and building graph.

        Returns:
            Tuple of (initial_state, start_time, run_id)
        """
        start_time = time.time()

        # Generate unique run_id if not provided
        if run_id is None:
            run_id = str(uuid.uuid4())

        logger.info(f"Starting hypothesis generation with run_id={run_id}")

        # Extract optional fields from opts
        opts = opts or {}
        user_inputs = opts.get("user_inputs") or {}

        # Determine if literature review node should be included
        # Check if explicitly set in opts first to avoid unnecessary MCP checks
        enable_literature_review_node_opt = opts.get("enable_literature_review_node")

        # Only check MCP availability if literature review node is requested (explicitly or by default)
        # If explicitly False, skip MCP checks entirely
        if enable_literature_review_node_opt is False:
            # Literature review explicitly disabled, no need to check MCP
            mcp_available = False
            pubmed_available = False
            enable_literature_review_node = False
        else:
            # Check system availability (cached per instance)
            from .mcp_client import check_mcp_available, check_pubmed_available_via_mcp

            # Lazy init: check once per instance on first call
            # Only check if we're running with literature review
            if self._mcp_available is None:
                self._mcp_available = await check_mcp_available()
            if self._pubmed_available is None:
                self._pubmed_available = await check_pubmed_available_via_mcp()

            # Use cached values
            mcp_available = self._mcp_available
            pubmed_available = self._pubmed_available

            # Determine if literature review node should be included
            # user can override via opts, otherwise auto-detect based on MCP availability
            enable_literature_review_node = opts.get("enable_literature_review_node", mcp_available)

            if not mcp_available and enable_literature_review_node:
                logger.warning(
                    "Literature review node requested but MCP server unavailable - disabling"
                )
                enable_literature_review_node = False

        # Determine if generate node should use tool-calling generation
        # user can override via opts, default False
        enable_tool_calling_generation = opts.get("enable_tool_calling_generation", False)

        # Validate: tool-calling generation requires literature review node + MCP
        if enable_tool_calling_generation:
            # Check MCP availability first - if unavailable, disable tool calling
            if not mcp_available:
                logger.warning(
                    "enable_tool_calling_generation=True but MCP server unavailable - disabling tool-calling mode"
                )
                enable_tool_calling_generation = False
            # Then check if literature review node is enabled
            # Only raise error if user explicitly disabled literature review but enabled tool calling
            elif not enable_literature_review_node:
                # Check if literature review was explicitly disabled by user
                if enable_literature_review_node_opt is False:
                    raise ValueError(
                        "enable_tool_calling_generation requires enable_literature_review_node=True. "
                        "Tool-calling generation needs literature context from the review node."
                    )
                else:
                    # Literature review was disabled due to MCP unavailability, disable tool calling
                    logger.warning(
                        "enable_tool_calling_generation=True but literature review node unavailable - disabling tool-calling mode"
                    )
                    enable_tool_calling_generation = False

        # dev isolation mode: force cache on lit review, allocate all to lit tools
        dev_test_lit_tools_isolation = opts.get("dev_test_lit_tools_isolation", False)
        if dev_test_lit_tools_isolation:
            logger.info(
                "Dev isolation mode enabled: forcing lit review cache + all hypotheses to lit tools"
            )

        # Build graph if not already built, or rebuild if literature review setting changed
        if self._graph is None:
            self._graph = self._build_graph(
                enable_literature_review_node=enable_literature_review_node
            )

        # Initialize state
        initial_state: WorkflowState = {
            "research_goal": research_goal,
            "model_name": self.model_name,
            "max_iterations": self.max_iterations,
            "initial_hypotheses_count": self.initial_hypotheses_count,
            "evolution_max_count": self.evolution_max_count,
            "hypotheses": [],
            "current_iteration": 0,
            "supervisor_guidance": {},
            "meta_review": {},
            "removed_duplicates": [],
            "tournament_matchups": [],
            "evolution_details": [],
            "metrics": ExecutionMetrics(),
            "start_time": start_time,
            "run_id": run_id,
            "progress_callback": progress_callback,
            "messages": [],
            # system availability flags
            "mcp_available": mcp_available,
            "pubmed_available": pubmed_available,
            "enable_tool_calling_generation": enable_tool_calling_generation,
            "dev_test_lit_tools_isolation": dev_test_lit_tools_isolation,
            # Optional user preferences and inputs
            "preferences": opts.get("preferences"),
            "attributes": opts.get("attributes"),
            "constraints": opts.get("constraints"),
            "starting_hypotheses": user_inputs.get("starting_hypotheses"),
            "literature": user_inputs.get("literature"),
        }

        return initial_state, start_time, run_id

    @overload
    def generate_hypotheses(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        stream: Literal[False] = False,
    ) -> Dict[str, Any]: ...

    @overload
    def generate_hypotheses(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        stream: Literal[True] = True,
    ) -> AsyncIterator[Tuple[str, Dict[str, Any]]]: ...

    def generate_hypotheses(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        stream: bool = False,
    ) -> Union[Dict[str, Any], AsyncIterator[Tuple[str, Dict[str, Any]]]]:
        """
        Generate hypotheses, with optional streaming.

        Args:
            research_goal: The research question or goal
            progress_callback: Async callback for progress updates
                             Called with (phase_name, data)
            opts: Optional dictionary with user preferences and inputs:
                - preferences: Desired approach or focus
                - attributes: Key qualities to prioritize
                - constraints: Requirements or boundaries
                - enable_literature_review_node: Whether to include literature review node (default: auto-detect MCP availability)
                - enable_tool_calling_generation: Enable tool-calling generation where generate node queries literature tools directly (requires enable_literature_review_node=True + MCP server, default: False)
                - dev_test_lit_tools_isolation: Dev mode - force lit review cache, all hypotheses to lit tools (default: False)
                - user_inputs: Dictionary with:
                  - starting_hypotheses: User-provided starting hypotheses
                  - literature: User-provided literature references
            run_id: Optional unique identifier for this run (generated if not provided)
            stream: If True, yields (node_name, state_dict) tuples. If False, returns final result dict.

        Returns:
            If stream=False: Coroutine that when awaited returns dictionary with results:
            {
                "hypotheses": [...],
                "meta_review": {...},
                "execution_time": 0.0,
                "metrics": {...}
            }

            If stream=True: AsyncIterator yielding (node_name, state_dict) tuples

        Example:
            >>> # Non-streaming
            >>> result = await generator.generate_hypotheses(research_goal="...", stream=False)
            >>>
            >>> # Streaming
            >>> async for node_name, state in generator.generate_hypotheses(research_goal="...", stream=True):
            >>>     print(f"Completed {node_name}")
        """
        if stream:
            # Streaming path: return async generator directly
            return self._generate_hypotheses_with_streaming(
                research_goal=research_goal,
                progress_callback=progress_callback,
                opts=opts,
                run_id=run_id,
            )
        else:
            # Non-streaming path: return coroutine to be awaited
            return self._generate_hypotheses_without_streaming(
                research_goal=research_goal,
                progress_callback=progress_callback,
                opts=opts,
                run_id=run_id,
            )

    async def _generate_hypotheses_without_streaming(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Internal method to handle non-streaming generation.

        Returns final result dictionary.
        """
        # Prepare generation (shared setup logic)
        initial_state, start_time, run_id = await self._prepare_generation(
            research_goal=research_goal,
            progress_callback=progress_callback,
            opts=opts,
            run_id=run_id,
        )

        try:
            # Run the workflow. Uses 100 recursion limit to support higher max iterations.
            final_state = await self._graph.ainvoke(initial_state, config={"recursion_limit": 100})

            # Format result to match expected interface
            execution_time = time.time() - start_time

            return {
                "hypotheses": [h.to_dict() for h in final_state["hypotheses"]],
                "meta_review": final_state.get("meta_review", {}),
                "research_plan": final_state.get("supervisor_guidance", {}),
                "tournament_matchups": final_state.get("tournament_matchups", []),
                "evolution_details": final_state.get("evolution_details", []),
                "debate_transcripts": final_state.get("debate_transcripts"),
                "execution_time": execution_time,
                "metrics": {
                    "total_time": execution_time,
                    "hypothesis_count": final_state["metrics"].hypothesis_count,
                    "reviews_count": final_state["metrics"].reviews_count,
                    "tournaments_count": final_state["metrics"].tournaments_count,
                    "evolutions_count": final_state["metrics"].evolutions_count,
                    "phase_times": final_state["metrics"].phase_times,
                    "llm_calls": final_state["metrics"].llm_calls,
                },
            }

        except Exception as e:
            logger.error(f"Hypothesis generation failed: {e}", exc_info=True)
            raise

    async def _generate_hypotheses_with_streaming(
        self,
        research_goal: str,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
        opts: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        """
        Internal method to handle streaming generation.

        Yields (node_name, state_dict) tuples after each node completes.
        """
        # Prepare generation (shared setup logic)
        initial_state, start_time, run_id = await self._prepare_generation(
            research_goal=research_goal,
            progress_callback=progress_callback,
            opts=opts,
            run_id=run_id,
        )

        # Delegate to streaming implementation
        async for node_name, state_dict in self._handle_streaming(initial_state, start_time):
            yield node_name, state_dict

    async def _handle_streaming(
        self,
        initial_state: WorkflowState,
        start_time: float,
    ) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        """
        Internal method to handle streaming generation.

        Args:
            initial_state: Prepared workflow state
            start_time: Start time for execution timing

        Yields:
            Tuple of (node_name, state_dict) after each node completes
        """
        try:
            # Maintain cumulative state across nodes
            # LangGraph's astream only yields fields updated by each node, not full state
            cumulative_state = {
                "hypotheses": [],
                "meta_review": {},
                "research_plan": {},
                "tournament_matchups": [],
                "evolution_details": [],
                "similarity_clusters": [],
                "current_iteration": 0,
                "metrics": ExecutionMetrics(),
                "articles_with_reasoning": None,
                "literature_review_queries": [],
                "articles": [],
                "debate_transcripts": None,
            }

            # Stream the workflow execution
            async for chunk in self._graph.astream(initial_state, config={"recursion_limit": 100}):
                # chunk is a dict with node names as keys
                for node_name, node_state in chunk.items():
                    logger.debug(f"streaming node: {node_name}")

                    # Update cumulative state with fields from this node
                    if "hypotheses" in node_state:
                        cumulative_state["hypotheses"] = node_state["hypotheses"]
                        logger.debug(f"updated hypotheses: {len(node_state['hypotheses'])} items")
                    if "meta_review" in node_state:
                        cumulative_state["meta_review"] = node_state["meta_review"]
                        logger.debug("updated meta_review")
                    if "supervisor_guidance" in node_state:
                        cumulative_state["research_plan"] = node_state["supervisor_guidance"]
                        logger.debug("updated research_plan")
                    if "tournament_matchups" in node_state:
                        cumulative_state["tournament_matchups"] = node_state["tournament_matchups"]
                        logger.debug(
                            f"updated tournament_matchups: {len(node_state['tournament_matchups'])} items"
                        )
                    if "evolution_details" in node_state:
                        cumulative_state["evolution_details"] = node_state["evolution_details"]
                        logger.debug(
                            f"updated evolution_details: {len(node_state['evolution_details'])} items"
                        )
                    if "similarity_clusters" in node_state:
                        cumulative_state["similarity_clusters"] = node_state["similarity_clusters"]
                        logger.debug("updated similarity_clusters")
                    if "current_iteration" in node_state:
                        cumulative_state["current_iteration"] = node_state["current_iteration"]
                        logger.debug(
                            f"updated current_iteration: {node_state['current_iteration']}"
                        )
                    if "metrics" in node_state:
                        # Import merge_metrics to properly combine metrics (don't just replace!)
                        from .state import merge_metrics

                        cumulative_state["metrics"] = merge_metrics(
                            cumulative_state["metrics"], node_state["metrics"]
                        )
                        logger.debug(
                            f"merged metrics: reviews={cumulative_state['metrics'].reviews_count}, "
                            f"tournaments={cumulative_state['metrics'].tournaments_count}, "
                            f"evolutions={cumulative_state['metrics'].evolutions_count}, "
                            f"llm_calls={cumulative_state['metrics'].llm_calls}"
                        )
                    if "articles_with_reasoning" in node_state:
                        cumulative_state["articles_with_reasoning"] = node_state[
                            "articles_with_reasoning"
                        ]
                        chars = (
                            len(node_state["articles_with_reasoning"])
                            if node_state["articles_with_reasoning"]
                            else 0
                        )
                        logger.debug(f"updated articles_with_reasoning: {chars} chars")
                    if "literature_review_queries" in node_state:
                        cumulative_state["literature_review_queries"] = node_state[
                            "literature_review_queries"
                        ]
                        logger.debug(
                            f"updated literature_review_queries: {len(node_state['literature_review_queries'])} queries"
                        )
                    if "articles" in node_state:
                        cumulative_state["articles"] = node_state["articles"]
                        logger.debug(f"updated articles: {len(node_state['articles'])} items")
                    if "debate_transcripts" in node_state:
                        cumulative_state["debate_transcripts"] = node_state["debate_transcripts"]
                        count = (
                            len(node_state["debate_transcripts"])
                            if node_state["debate_transcripts"]
                            else 0
                        )
                        logger.debug(f"updated debate_transcripts: {count} debates")

                    # Yield the node name and CUMULATIVE state
                    state_dict = {
                        "hypotheses": [h.to_dict() for h in cumulative_state["hypotheses"]],
                        "meta_review": cumulative_state["meta_review"],
                        "research_plan": cumulative_state["research_plan"],
                        "tournament_matchups": cumulative_state["tournament_matchups"],
                        "evolution_details": cumulative_state["evolution_details"],
                        "similarity_clusters": cumulative_state["similarity_clusters"],
                        "current_iteration": cumulative_state["current_iteration"],
                        "articles_with_reasoning": cumulative_state["articles_with_reasoning"],
                        "literature_review_queries": cumulative_state["literature_review_queries"],
                        "articles": [a.to_dict() for a in cumulative_state["articles"]],
                        "debate_transcripts": cumulative_state["debate_transcripts"],
                        "metrics": {
                            "hypothesis_count": cumulative_state["metrics"].hypothesis_count,
                            "reviews_count": cumulative_state["metrics"].reviews_count,
                            "tournaments_count": cumulative_state["metrics"].tournaments_count,
                            "evolutions_count": cumulative_state["metrics"].evolutions_count,
                            "llm_calls": cumulative_state["metrics"].llm_calls,
                        },
                    }

                    logger.debug(f"yielding state for node: {node_name}")

                    yield node_name, state_dict

        except Exception as e:
            logger.error(f"Hypothesis generation streaming failed: {e}", exc_info=True)
            raise


# Export for backwards compatibility
__all__ = ["HypothesisGenerator"]
