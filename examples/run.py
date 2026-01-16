"""
Example for Open Coscientist with streaming output.

This demonstrates hypothesis generation with literature review integration,
showing real-time streaming of results as they're generated.
"""
import os
import sys
# allow running example without installing the package
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")),
)
from open_coscientist import HypothesisGenerator
from open_coscientist.console import ConsoleReporter, default_progress_callback, run_console
from rich.console import Console
from rich.panel import Panel
"""
Prerequisites:
- MCP server running (on http://localhost:8888/mcp)
- Set OPEN_AI_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in your environment before running,
which depends on the MODEL_NAME you set below.
"""

MODEL_NAME = "gemini/gemini-2.5-flash"

async def main():
    # Prompt user for research goal with rich formatting
    console = Console()
    console.print()
    console.print(
        Panel(
            "[bold]Enter research goal[/bold]\n\n"
            "[dim]For example:[/dim] Develop novel approaches for early detection of "
            "Alzheimer's disease using non-invasive biomarkers",
            title="[cyan]Research Goal[/cyan]",
            border_style="cyan",
        )
    )
    research_goal = console.input("\n[bold cyan]Research goal:[/bold cyan] ").strip()
    if not research_goal:
        console.print("[bold red]Error:[/bold red] Research goal cannot be empty.")
        return
    generator = HypothesisGenerator(
        model_name=MODEL_NAME,
        max_iterations=2,
        initial_hypotheses_count=7,
        evolution_max_count=4,
    )

    # for rich terminal output
    reporter = ConsoleReporter()

    # wrap with built-in console/terminal reporter
    await reporter.run(
        event_stream=generator.generate_hypotheses(
            research_goal=research_goal,
            progress_callback=default_progress_callback,
            # explicitly enable literature review/generate with tool calling
            opts={
                "enable_literature_review_node": True,
                "enable_tool_calling_generation": True,
            },
            stream=True,
        ),
        research_goal=research_goal,
    )


if __name__ == "__main__":
    # wrap with run_console for graceful shutdown on KeyboardInterrupt and hide internal warnings
    run_console(main())