"""
Test supervisor node in isolation.

Simplest node to test - no dependencies, just creates research plan.
"""

import asyncio
import json
from rich.console import Console
from rich.panel import Panel
from rich.json import JSON

from state_helpers import make_base_state
from open_coscientist.nodes.supervisor import supervisor_node


console = Console()


async def test_supervisor():
    """Run supervisor node with minimal state."""

    console.print("\n[bold cyan]Testing supervisor node[/bold cyan]\n")

    # Create minimal state
    state = make_base_state(
        research_goal="How can we detect Alzheimer's disease earlier using retinal imaging?",
        model_name="gemini/gemini-2.5-flash",
    )

    console.print(f"[yellow]Research goal:[/yellow] {state['research_goal']}\n")

    # Run node
    console.print("[yellow]Calling supervisor node...[/yellow]\n")
    result = await supervisor_node(state)

    # Display results
    guidance = result.get("supervisor_guidance", {})

    console.print(Panel(
        JSON(json.dumps(guidance, indent=2)),
        title="[bold green]Supervisor guidance output[/bold green]",
        border_style="green"
    ))

    # Show what would be passed to next nodes
    console.print("\n[bold]Key fields for downstream nodes:[/bold]")
    console.print(f"  approach_description: {len(guidance.get('approach_description', ''))} chars")
    console.print(f"  key_considerations: {len(guidance.get('key_considerations', []))} items")
    console.print(f"  search_strategy: {len(guidance.get('search_strategy', {}))} keys")


if __name__ == "__main__":
    asyncio.run(test_supervisor())
