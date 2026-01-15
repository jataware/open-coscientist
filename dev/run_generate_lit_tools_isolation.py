"""
test generate node with lit tools in isolation mode.

this script enables dev isolation mode which:
1. forces cache on lit review node (fast, no mcp calls)
2. allocates all hypotheses to lit tools generation (no debate)
3. skips generate node cache (see real tool-based output)

useful for debugging the two-phase tool-based generation without
distraction from debate output or slow lit review calls.
"""

import asyncio
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from state_helpers import make_supervisor_state
from open_coscientist.nodes.literature_review import literature_review_node
from open_coscientist.nodes.generate import generate_node


console = Console()


async def test_lit_tools_isolation(research_goal: str, model_name: str, hypotheses_count: int = 3):
    """
    run generate node with lit tools in isolation mode.

    args:
        research_goal: research question
        model_name: llm model to use
        hypotheses_count: number of hypotheses to generate
    """

    console.print("\n[bold cyan]testing generate node with lit tools (isolation mode)[/bold cyan]\n")

    # disable global cache so we see fresh generate output
    os.environ["COSCIENTIST_CACHE_ENABLED"] = "false"
    console.print("[yellow]global cache disabled (will see fresh generate output)[/yellow]")

    # create base state with supervisor
    console.print("[yellow]preparing state (running supervisor first)...[/yellow]")
    state = make_supervisor_state(research_goal=research_goal, model_name=model_name)
    state["initial_hypotheses_count"] = hypotheses_count

    # enable lit tools generation
    state["enable_tool_calling_generation"] = True
    console.print("[green]enabled: tool_calling_generation=True[/green]")

    # enable dev isolation mode (force lit review cache + no debate)
    state["dev_test_lit_tools_isolation"] = True
    console.print("[green]enabled: dev_test_lit_tools_isolation=True[/green]")
    console.print("  - lit review will use cache (fast)")
    console.print("  - all hypotheses allocated to lit tools (no debate)\n")

    # run lit review node (will use cache if available)
    console.print("[yellow]running literature review node (with forced cache)...[/yellow]")
    lit_result = await literature_review_node(state)
    state.update(lit_result)

    if state.get("articles_with_reasoning"):
        console.print(f"[green]literature review complete: {len(state.get('articles', []))} articles found[/green]")
    else:
        console.print("[red]error: no literature review data available[/red]")
        return

    console.print(f"\n[yellow]research goal:[/yellow] {state['research_goal']}")
    console.print(f"[yellow]hypotheses to generate:[/yellow] {state['initial_hypotheses_count']}")
    console.print(f"[yellow]model:[/yellow] {state['model_name']}\n")

    # run generate node with lit tools
    console.print("[yellow]calling generate node with lit tools (this may take 2-3 minutes)...[/yellow]")
    console.print("[dim]phase 1: draft hypotheses by reading papers[/dim]")
    console.print("[dim]phase 2: validate novelty by searching literature[/dim]\n")

    result = await generate_node(state)

    # display results
    hypotheses = result.get("hypotheses", [])

    # hypotheses table
    hyp_table = Table(title=f"generated hypotheses ({len(hypotheses)} total)")
    hyp_table.add_column("id", style="cyan", width=10)
    hyp_table.add_column("hypothesis", style="white", max_width=60)
    hyp_table.add_column("generation_method", style="yellow", width=20)

    for hyp in hypotheses:
        hyp_table.add_row(
            hyp.id,
            hyp.text[:60] + "..." if len(hyp.text) > 60 else hyp.text,
            hyp.generation_method or "unknown",
        )

    console.print(hyp_table)

    # show first hypothesis in detail
    if hypotheses:
        first = hypotheses[0]
        console.print(Panel(
            Markdown(f"""
**hypothesis text:**
{first.text}

**justification:**
{first.justification or 'none'}

**literature review used:**
{first.literature_review_used or 'none'}

**novelty validation:**
{first.novelty_validation or 'none'}

**generation method:** {first.generation_method or 'unknown'}
"""),
            title=f"[bold green]first hypothesis details[/bold green]",
            border_style="green"
        ))

    # verify all are lit tools generated
    lit_tools_count = sum(1 for h in hypotheses if h.generation_method == "literature_tools")
    debate_count = sum(1 for h in hypotheses if h.generation_method == "debate")

    console.print(f"\n[bold]summary stats:[/bold]")
    console.print(f"  hypotheses generated: {len(hypotheses)}")
    console.print(f"  lit tools: {lit_tools_count}")
    console.print(f"  debate: {debate_count}")

    if debate_count > 0:
        console.print("\n[red]warning: expected 0 debate hypotheses in isolation mode, got {debate_count}[/red]")
    if lit_tools_count != len(hypotheses):
        console.print(f"[red]warning: expected all hypotheses to be lit_tools, got {lit_tools_count}/{len(hypotheses)}[/red]")

    if lit_tools_count == len(hypotheses):
        console.print("\n[bold green]success: all hypotheses generated with lit tools![/bold green]")


if __name__ == "__main__":
    import sys

    # default research goal
    research_goal = "How can we detect Alzheimer's disease earlier using retinal imaging?"

    # check for custom research goal
    if len(sys.argv) > 1 and sys.argv[1] not in ["--model", "--count"]:
        research_goal = sys.argv[1]

    # parse optional flags
    model_name = "gemini/gemini-2.5-flash"
    hypotheses_count = 3

    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model_name = sys.argv[i + 1]
        elif arg == "--count" and i + 1 < len(sys.argv):
            hypotheses_count = int(sys.argv[i + 1])

    asyncio.run(test_lit_tools_isolation(
        research_goal=research_goal,
        model_name=model_name,
        hypotheses_count=hypotheses_count
    ))
