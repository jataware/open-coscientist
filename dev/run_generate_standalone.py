"""
Test generate node in isolation.

Depends on supervisor node output (will run supervisor first).
Optionally can test with literature review results.
"""

import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from state_helpers import make_generate_state
from open_coscientist.nodes.generate import generate_node


console = Console()

RESEARCH_GOAL = "How can we detect Alzheimer's disease earlier using retinal imaging?"
MODEL_NAME = "gemini/gemini-2.5-flash"


async def test_generate(with_literature: bool = False):
    """
    Run generate node with minimal state.

    Args:
        with_literature: if True, includes mocked literature review data
    """

    console.print("\n[bold cyan]Testing generate node[/bold cyan]\n")

    # Create state with supervisor + optional literature
    console.print("[yellow]Preparing state (running supervisor first)...[/yellow]")
    state = make_generate_state(
        research_goal=RESEARCH_GOAL,
        model_name=MODEL_NAME,
        with_literature=with_literature,
    )

    if with_literature:
        console.print("[green]Using mocked literature review data[/green]")
    else:
        console.print("[yellow]No literature review data[/yellow]")

    console.print(f"\n[yellow]research goal:[/yellow] {state['research_goal']}")
    console.print(f"[yellow]hypotheses to generate:[/yellow] {state['initial_hypotheses_count']}\n")

    # run node
    console.print("[yellow]calling generate node (this may take 1-2 minutes)...[/yellow]\n")
    result = await generate_node(state)

    # display results
    hypotheses = result.get("hypotheses", [])
    debate_transcripts = result.get("debate_transcripts", [])

    # hypotheses table
    hyp_table = Table(title=f"generated hypotheses ({len(hypotheses)} total)")
    hyp_table.add_column("id", style="cyan", width=10)
    hyp_table.add_column("hypothesis", style="white", max_width=60)
    hyp_table.add_column("generation_method", style="yellow", width=20)

    for hyp in hypotheses:
        hyp_table.add_row(
            hyp.id,
            hyp.text[:60] + "..." if len(hyp.text) > 60 else hyp.text,
            hyp.generation_method or "standard",
        )

    console.print(hyp_table)

    # show first hypothesis in detail
    if hypotheses:
        first = hypotheses[0]
        console.print(Panel(
            Markdown(f"""
**hypothesis text:**
{first.text}

**rationale:**
{first.rationale}

**generation method:** {first.generation_method or 'standard'}
"""),
            title=f"[bold green]first hypothesis details[/bold green]",
            border_style="green"
        ))

    # debate info
    if debate_transcripts:
        console.print(f"\n[bold]debate transcripts:[/bold] {len(debate_transcripts)} debates recorded")
        console.print(f"  example debate turns: {len(debate_transcripts[0].get('debate_turns', []))} turns")

    console.print(f"\n[bold]summary stats:[/bold]")
    console.print(f"  hypotheses generated: {len(hypotheses)}")
    console.print(f"  debate-based: {sum(1 for h in hypotheses if h.generation_method == 'debate')}")
    console.print(f"  literature-based: {sum(1 for h in hypotheses if h.generation_method == 'literature')}")
    console.print(f"  standard: {sum(1 for h in hypotheses if not h.generation_method or h.generation_method == 'standard')}")


if __name__ == "__main__":
    import sys

    # check for --with-literature flag
    with_lit = "--with-literature" in sys.argv

    asyncio.run(test_generate(with_literature=with_lit))
