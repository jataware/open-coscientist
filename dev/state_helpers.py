"""
Minimal state builders for testing nodes in isolation.

These create the bare minimum state required to run a node without errors.
Intentionally kept minimal to avoid mock data drift - add fields as needed.
"""

import time
from typing import Optional, List, Dict, Any
from rich.console import Console
from open_coscientist.state import WorkflowState
from open_coscientist.models import ExecutionMetrics, Hypothesis

console = Console()


def make_base_state(
    research_goal: str = "How can we detect Alzheimer's disease earlier using retinal imaging?",
    model_name: str = "gemini/gemini-2.5-flash",
    initial_hypotheses_count: int = 3,
    max_iterations: int = 0,
) -> WorkflowState:
    """
    Minimal state with just required fields.

    Use this for nodes that don't depend on previous nodes (eg supervisor).
    """
    return {
        "research_goal": research_goal,
        "model_name": model_name,
        "max_iterations": max_iterations,
        "initial_hypotheses_count": initial_hypotheses_count,
        "evolution_max_count": 2,
        "hypotheses": [],
        "current_iteration": 0,
        "supervisor_guidance": {},
        "meta_review": {},
        "removed_duplicates": [],
        "tournament_matchups": [],
        "evolution_details": [],
        "metrics": ExecutionMetrics(),
        "start_time": time.time(),
        "run_id": f"dev-test-{int(time.time())}",
        "progress_callback": None,
        "messages": [],
        "mcp_available": False,
        "pubmed_available": False,
    }


def make_supervisor_state(
    research_goal: str = "How can we detect Alzheimer's disease earlier using retinal imaging?",
    model_name: str = "gemini/gemini-2.5-flash",
) -> WorkflowState:
    """
    Base state with supervisor guidance populated.

    Use this for nodes that depend on supervisor output (eg generate node).
    Note: this creates a REAL supervisor output by calling the supervisor node.
    """
    from open_coscientist.nodes.supervisor import supervisor_node
    import asyncio

    base = make_base_state(research_goal, model_name)

    # Run supervisor to get real guidance
    console.print("[dim]Running supervisor node to create realistic state...[/dim]")
    result = asyncio.run(supervisor_node(base))

    base.update(result)
    console.print(f"[dim]Supervisor guidance keys: {list(base['supervisor_guidance'].keys())}[/dim]")

    return base


def make_literature_state(
    research_goal: str = "How can we detect Alzheimer's disease earlier using retinal imaging?",
    model_name: str = "gemini/gemini-2.5-flash",
    run_real_lit_review: bool = False,
) -> WorkflowState:
    """
    Base state with literature review results populated.

    Use this for nodes that depend on literature review (eg reflection node).

    Args:
        run_real_lit_review: if True, calls real lit review node (requires MCP server)
                            if False, uses minimal mock data
    """
    from open_coscientist.nodes.literature_review import literature_review_node
    from open_coscientist.models import Article
    import asyncio

    base = make_base_state(research_goal, model_name)

    if run_real_lit_review:
        console.print("[dim]Running literature review node to create realistic state...[/dim]")
        console.print("[dim](Requires MCP server available)[/dim]")
        result = asyncio.run(literature_review_node(base))
        base.update(result)
    else:
        # Minimal mock data - just enough to not error
        base["articles_with_reasoning"] = """
## literature review summary

### key finding 1
retinal imaging shows promise for early alzheimer's detection

### key finding 2
microvasculature changes appear years before cognitive symptoms
"""
        base["literature_review_queries"] = [
            "alzheimer's disease retinal imaging biomarkers",
            "early detection cognitive decline optical coherence tomography"
        ]
        base["articles"] = [
            Article(
                title="retinal biomarkers for alzheimer's disease",
                authors=["smith j", "doe a"],
                year=2023,
                abstract="study on retinal changes in ad patients",
                citation_count=42,
                url="https://example.com/paper1",
                relevance_score=0.95,
            )
        ]

    return base


def make_generate_state(
    research_goal: str = "How can we detect Alzheimer's disease earlier using retinal imaging?",
    model_name: str = "gemini/gemini-2.5-flash",
    with_literature: bool = False,
) -> WorkflowState:
    """
    State ready for generate node with supervisor + optional literature.

    Use this for testing generate node directly.
    """
    state = make_supervisor_state(research_goal, model_name)

    if with_literature:
        lit_state = make_literature_state(research_goal, model_name, run_real_lit_review=False)
        state["articles_with_reasoning"] = lit_state["articles_with_reasoning"]
        state["literature_review_queries"] = lit_state["literature_review_queries"]
        state["articles"] = lit_state["articles"]

    return state
