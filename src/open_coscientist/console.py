"""
Console reporter for rich terminal output.

Provides pretty-printed progress and results for hypothesis generation using Rich formatting.
"""

import asyncio
import json
import logging
import sys
import time
import warnings
from typing import Any, AsyncIterator, Coroutine, Dict, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .constants import LITERATURE_REVIEW_FAILED


class FilteredStderr:
    """Filter out SSL cleanup errors from stderr."""

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.skip_patterns = [
            "Fatal error on SSL transport",
            "OSError: [Errno 9] Bad file descriptor",
            "RuntimeError: Event loop is closed",
            "Traceback (most recent call last):",
            "File \"/Users/",
            "File \"/usr/",
            "_SelectorSocketTransport",
            "raise RuntimeError",
            "asyncio/sslproto.py",
            "asyncio/selector_events.py",
            "asyncio/base_events.py",
        ]
        self.buffer = ""
        self.skip_block = False

    def write(self, text):
        # accumulate text
        self.buffer += text

        # check if we should skip this block
        for pattern in self.skip_patterns:
            if pattern in self.buffer:
                self.skip_block = True
                break

        # if we hit a newline, decide whether to output
        if "\n" in text:
            if not self.skip_block:
                self.original_stderr.write(self.buffer)
                self.original_stderr.flush()
            self.buffer = ""
            self.skip_block = False

    def flush(self):
        if self.buffer and not self.skip_block:
            self.original_stderr.write(self.buffer)
            self.buffer = ""
        self.original_stderr.flush()


def get_generation_method_badge(method: str) -> str:
    """Get a colored badge for the generation method."""
    if method == "debate":
        return "[magenta][DEBATE][/magenta]"
    elif method == "literature":
        return "[cyan][LITERATURE][/cyan]"
    elif method == "literature_tools":
        return "[green][LITERATURE TOOLS][/green]"
    elif method == "standard":
        return "[blue][STANDARD][/blue]"
    else:
        return ""


async def default_progress_callback(phase: str, data: dict):
    """Simple progress callback that prints updates."""
    console = Console()
    console.print(f" [dim cyan]{data.get('message', '')}[/dim cyan]")
    console.file.flush()


class ConsoleReporter:
    """
    Rich console reporter for hypothesis generation workflow.

    Handles streaming events from HypothesisGenerator and displays them
    with rich formatting (tables, panels, colors) in the terminal.

    Example:
        >>> generator = HypothesisGenerator(...)
        >>> reporter = ConsoleReporter()
        >>> result = await reporter.run(
        ...     generator.generate_hypotheses(research_goal="...", stream=True)
        ... )
    """

    def __init__(self, console: Optional[Console] = None, filter_stderr: bool = True):
        """
        Initialize console reporter.

        Args:
            console: Rich console instance (creates new one if None)
            filter_stderr: Whether to filter SSL/asyncio cleanup errors from stderr
        """
        self.console = console or Console()
        self.filter_stderr = filter_stderr

        # track what we've displayed to avoid duplicates
        self._displayed_research_plan = False
        self._displayed_literature_review = False
        self._displayed_meta_review = False
        self._displayed_hypotheses = {}

        # original stderr for restoration
        self._original_stderr = None

    async def run(
        self,
        event_stream: AsyncIterator[Tuple[str, Dict[str, Any]]],
        research_goal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the reporter on a streaming event source.

        Args:
            event_stream: Async iterator yielding (node_name, state) tuples
            research_goal: Optional research goal to display in header

        Returns:
            Final state dictionary with results
        """
        # setup stderr filtering if enabled
        if self.filter_stderr:
            self._original_stderr = sys.stderr
            sys.stderr = FilteredStderr(self._original_stderr)

        try:
            start_time = time.time()
            last_state = None

            # show header
            self.console.rule("[bold blue]Open Coscientist - Hypothesis Generation[/bold blue]")
            self.console.print()

            if research_goal:
                self.console.print(
                    Panel(
                        f"[bold]{research_goal}[/bold]",
                        title="[cyan]Research Goal[/cyan]",
                        border_style="cyan",
                    )
                )
                self.console.print()

            # process streaming events
            async for node_name, state in event_stream:
                last_state = state
                await self._handle_event(node_name, state)

            # show final summary
            execution_time = time.time() - start_time
            self._show_final_summary(last_state, execution_time)

            # give time for connections to close gracefully
            await asyncio.sleep(0.5)

            return last_state

        finally:
            # restore original stderr
            if self.filter_stderr and self._original_stderr:
                sys.stderr = self._original_stderr

    async def _handle_event(self, node_name: str, state: Dict[str, Any]):
        """Handle a single workflow event."""
        if node_name == "supervisor":
            self._show_research_plan(state)
        elif node_name == "literature_review":
            self._show_literature_review(state)
        elif node_name == "generate":
            self._show_generated_hypotheses(state)
        elif node_name == "review":
            self._show_reviews(state)
        elif node_name == "rank":
            self._show_rankings(state)
        elif node_name == "tournament":
            self._show_tournament(state)
        elif node_name == "meta_review":
            self._show_meta_review(state)
        elif node_name == "evolve":
            self._show_evolution(state)

    def _show_research_plan(self, state: Dict[str, Any]):
        """Display research plan from supervisor."""
        if self._displayed_research_plan:
            return

        if state.get("research_plan"):
            self.console.print()
            self.console.rule("[bold magenta]Research Plan[/bold magenta]")
            self.console.print(
                Panel(
                    Syntax(
                        json.dumps(state["research_plan"], indent=2),
                        "json",
                        theme="monokai",
                    ),
                    title="[magenta]From Supervisor[/magenta]",
                    border_style="magenta",
                    expand=False,
                )
            )
            self.console.file.flush()
            self._displayed_research_plan = True

    def _show_literature_review(self, state: Dict[str, Any]):
        """Display literature review results."""
        if self._displayed_literature_review:
            return

        lit_review = state.get("articles_with_reasoning")
        if lit_review:
            self.console.print()
            self.console.rule("[bold cyan]Literature Review[/bold cyan]")

            # check if literature review failed
            if lit_review == LITERATURE_REVIEW_FAILED:
                self.console.print(
                    Panel(
                        "[bold red]Literature review failed![/bold red]\n\n"
                        "The system will fall back to standard generation without literature context.",
                        title="[red]Literature Review Failed[/red]",
                        border_style="red",
                        expand=False,
                    )
                )
            else:
                # display successful literature review
                self.console.print(
                    Panel(
                        lit_review[:2000] + ("..." if len(lit_review) > 2000 else ""),
                        title="[cyan]Literature Analysis (truncated)[/cyan]",
                        border_style="cyan",
                        expand=False,
                    )
                )
            self.console.file.flush()
            self._displayed_literature_review = True

    def _show_generated_hypotheses(self, state: Dict[str, Any]):
        """Display initial hypotheses when generated."""
        for i, hyp in enumerate(state.get("hypotheses", []), 1):
            hyp_key = hyp["text"][:100]
            if hyp_key in self._displayed_hypotheses:
                continue

            self._displayed_hypotheses[hyp_key] = hyp

            # get generation method badge
            method_badge = get_generation_method_badge(hyp.get("generation_method"))
            title = f"[bold cyan]Initial Hypothesis {i}[/bold cyan] {method_badge}"

            self.console.print()
            self.console.rule(title)

            # show hypothesis text
            hyp_content = f"[bold]Text:[/bold]\n{hyp['text']}"

            # add literature reference if available
            if hyp.get("literature_review_used"):
                hyp_content += f"\n\n[dim]Literature Reference:[/dim]\n{hyp['literature_review_used'][:200]}..."

            self.console.print(Panel(hyp_content, border_style="cyan", expand=True))
            self.console.file.flush()

    def _show_reviews(self, state: Dict[str, Any]):
        """Display reviews after review phase."""
        for i, hyp in enumerate(state.get("hypotheses", []), 1):
            if hyp.get("reviews"):
                latest_review = hyp["reviews"][-1]
                self.console.print()
                self.console.rule(f"[bold yellow]Review for Hypothesis {i}[/bold yellow]")

                if latest_review.get("scores"):
                    table = Table(
                        title="Review Scores", show_header=True, header_style="bold magenta"
                    )
                    table.add_column("Criterion", style="cyan")
                    table.add_column("Score", style="yellow", justify="right")

                    for criterion, score in latest_review["scores"].items():
                        table.add_row(criterion, f"{score:.2f}")

                    self.console.print(table)

                if latest_review.get("review_summary"):
                    self.console.print(
                        Panel(
                            latest_review["review_summary"],
                            title="[yellow]Review Summary[/yellow]",
                            border_style="yellow",
                        )
                    )

                self.console.file.flush()

    def _show_rankings(self, state: Dict[str, Any]):
        """Display ranking results."""
        self.console.print()
        self.console.rule("[bold green]Ranking Results[/bold green]")
        rank_table = Table(title="Hypothesis Rankings", show_header=True, header_style="bold green")
        rank_table.add_column("Rank", style="cyan", justify="right")
        rank_table.add_column("Score", style="yellow", justify="right")
        rank_table.add_column("Hypothesis (truncated)", style="white")

        sorted_hyps = sorted(
            state.get("hypotheses", []), key=lambda h: h.get("score", 0), reverse=True
        )
        for rank, hyp in enumerate(sorted_hyps, 1):
            rank_table.add_row(
                str(rank),
                f"{hyp.get('score', 0):.2f}",
                hyp["text"][:80] + "..." if len(hyp["text"]) > 80 else hyp["text"],
            )

        self.console.print(rank_table)
        self.console.file.flush()

    def _show_tournament(self, state: Dict[str, Any]):
        """Display tournament results."""
        # show matchup details with reasoning first
        matchups = state.get("tournament_matchups", [])
        if matchups:
            self.console.print()
            self.console.rule("[bold magenta]Tournament Matchups[/bold magenta]")
            for i, matchup in enumerate(matchups, 1):
                self.console.print()
                self.console.print(f"[bold cyan]Matchup {i}:[/bold cyan]")
                self.console.print(
                    Panel(
                        f"[bold yellow]Hypothesis A:[/bold yellow]\n{matchup['hypothesis_a'][:150] + '...' if len(matchup['hypothesis_a']) > 150 else matchup['hypothesis_a']}\n\n"
                        f"[bold yellow]Hypothesis B:[/bold yellow]\n{matchup['hypothesis_b'][:150] + '...' if len(matchup['hypothesis_b']) > 150 else matchup['hypothesis_b']}\n\n"
                        f"[bold green]Winner: {matchup['winner'].upper()}[/bold green]\n\n"
                        f"[bold]Reasoning:[/bold]\n{matchup['reasoning']}\n\n"
                        f"[dim]Elo Changes:[/dim]\n"
                        f"[dim]Winner: {matchup['winner_elo_before']} → {matchup['winner_elo_after']} ({matchup['winner_elo_after'] - matchup['winner_elo_before']:+d})[/dim]\n"
                        f"[dim]Loser: {matchup['loser_elo_before']} → {matchup['loser_elo_after']} ({matchup['loser_elo_after'] - matchup['loser_elo_before']:+d})[/dim]",
                        border_style="magenta",
                        expand=True,
                    )
                )
            self.console.file.flush()

        # then show final Elo rankings after matchups
        self.console.print()
        self.console.rule("[bold magenta]Tournament Results (Elo Ratings)[/bold magenta]")
        elo_table = Table(
            title="Updated Elo Rankings (Post-Tournament)",
            show_header=True,
            header_style="bold magenta",
        )
        elo_table.add_column("Rank", style="cyan", justify="right")
        elo_table.add_column("Elo Rating", style="yellow", justify="right")
        elo_table.add_column("Hypothesis (truncated)", style="white")

        sorted_hyps = sorted(
            state.get("hypotheses", []),
            key=lambda h: h.get("elo_rating", 1200),
            reverse=True,
        )
        for rank, hyp in enumerate(sorted_hyps, 1):
            elo_table.add_row(
                str(rank),
                str(hyp.get("elo_rating", 1200)),
                hyp["text"][:80] + "..." if len(hyp["text"]) > 80 else hyp["text"],
            )

        self.console.print(elo_table)
        self.console.file.flush()

    def _show_meta_review(self, state: Dict[str, Any]):
        """Display meta review."""
        if self._displayed_meta_review:
            return

        if state.get("meta_review"):
            self.console.print()
            self.console.rule("[bold blue]Meta Review[/bold blue]")
            self.console.print(
                Panel(
                    Syntax(json.dumps(state["meta_review"], indent=2), "json", theme="monokai"),
                    title="[blue]Cross-hypothesis Insights[/blue]",
                    border_style="blue",
                    expand=False,
                )
            )
            self.console.file.flush()
            self._displayed_meta_review = True

    def _show_evolution(self, state: Dict[str, Any]):
        """Display evolved hypotheses with detailed rationale."""
        evolution_details = state.get("evolution_details", [])

        if evolution_details:
            self.console.print()
            self.console.rule("[bold green]Evolution Details[/bold green]")

            for i, detail in enumerate(evolution_details, 1):
                self.console.print()
                self.console.print(f"[bold green]Evolution {i}:[/bold green]")
                self.console.print(
                    Panel(
                        f"[bold yellow]Original Hypothesis:[/bold yellow]\n{detail['original']}\n\n"
                        f"[bold green]Evolved Hypothesis:[/bold green]\n{detail['evolved']}\n\n"
                        f"[bold]Evolution Rationale:[/bold]\n{detail['rationale']}",
                        border_style="green",
                        expand=True,
                    )
                )

                # show key changes if available
                if detail.get("changes"):
                    self.console.print("\n[bold]Key Changes:[/bold]")
                    for change in detail["changes"]:
                        self.console.print(f"  • {change}")

                # show improvements if available
                if detail.get("improvements"):
                    self.console.print("\n[bold]Improvements:[/bold]")
                    for improvement in detail["improvements"]:
                        self.console.print(f"  • {improvement}")

                self.console.file.flush()
        else:
            self.console.print()
            self.console.print(
                "[dim yellow]No hypotheses were significantly evolved (changes too similar to existing)[/dim yellow]"
            )
            self.console.file.flush()

    def _show_final_summary(self, last_state: Optional[Dict[str, Any]], execution_time: float):
        """Display final results summary."""
        self.console.print()
        self.console.rule("[bold green]FINAL RESULTS[/bold green]")

        if last_state and last_state.get("hypotheses"):
            sorted_final = sorted(
                last_state["hypotheses"],
                key=lambda h: h.get("elo_rating", 1200),
                reverse=True,
            )

            for i, hyp in enumerate(sorted_final, 1):
                # get generation method badge
                method_badge = get_generation_method_badge(hyp.get("generation_method"))
                title = f"[bold cyan]Final Hypothesis {i}[/bold cyan] {method_badge}"

                # build stats line with tournament info
                stats_parts = [
                    f"[bold]Score:[/bold] {hyp.get('score', 0):.2f}",
                    f"[bold]Elo:[/bold] {hyp.get('elo_rating', 1200)}",
                    f"[bold]Reviews:[/bold] {len(hyp.get('reviews', []))}",
                ]

                # add tournament stats if available
                win_count = hyp.get("win_count", 0)
                loss_count = hyp.get("loss_count", 0)
                total_matches = hyp.get("total_matches", 0)
                if total_matches > 0:
                    win_rate = hyp.get("win_rate", 0)
                    stats_parts.append(
                        f"[bold]Tournament:[/bold] {win_count}W-{loss_count}L ({win_rate:.1f}%)"
                    )

                stats_line = " | ".join(stats_parts)

                self.console.print()
                self.console.rule(title)
                self.console.print(
                    Panel(
                        f"[bold]Text:[/bold]\n{hyp['text']}\n\n{stats_line}",
                        border_style="cyan",
                        expand=True,
                    )
                )

                # show all reviews
                if hyp.get("reviews"):
                    for review_num, review in enumerate(hyp["reviews"], 1):
                        self.console.print(f"\n[bold yellow]Review {review_num}:[/bold yellow]")

                        if review.get("scores"):
                            table = Table(show_header=True, header_style="bold magenta")
                            table.add_column("Criterion", style="cyan")
                            table.add_column("Score", style="yellow", justify="right")

                            for criterion, score in review["scores"].items():
                                table.add_row(criterion, f"{score:.2f}")

                            self.console.print(table)

                        if review.get("review_summary"):
                            self.console.print(
                                Panel(review["review_summary"], border_style="yellow")
                            )

                self.console.file.flush()

        self.console.print()
        self.console.rule("[bold green]COMPLETED[/bold green]")
        self.console.print(
            Panel(
                f"[bold]Total Execution Time:[/bold] {execution_time:.2f} seconds\n"
                f"[bold]Final Hypotheses:[/bold] {len(last_state.get('hypotheses', [])) if last_state else 0}",
                title="[green]Summary[/green]",
                border_style="green",
            )
        )
        self.console.file.flush()


class SSLCleanupFilter(logging.Filter):
    """Filter out SSL transport and event loop cleanup errors from asyncio."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to suppress the log record, True to allow it."""
        if record.name == "asyncio":
            message = record.getMessage()
            # suppress SSL transport errors during cleanup
            if any(pattern in message for pattern in [
                "Fatal error on SSL transport",
                "Bad file descriptor",
                "Event loop is closed",
                "SSLProtocol",
            ]):
                return False
        return True


def run_console(coro: Coroutine) -> None:
    """
    Run an async coroutine with graceful shutdown handling for console apps.

    This helper manages event loop lifecycle and ensures clean exits when
    Ctrl+C is pressed, preventing ugly SSL/socket error tracebacks.

    Args:
        coro: The async coroutine to run (e.g., main())

    Example:
        async def main():
            generator = HypothesisGenerator(...)
            reporter = ConsoleReporter()
            await reporter.run(...)

        if __name__ == "__main__":
            run_console(main())
    """
    # suppress RuntimeWarnings from LiteLLM's async cleanup during shutdown
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="litellm")

    # suppress asyncio SSL cleanup errors at the logging level
    asyncio_logger = logging.getLogger("asyncio")
    ssl_filter = SSLCleanupFilter()
    asyncio_logger.addFilter(ssl_filter)

    # use manual event loop management for graceful shutdown
    # this prevents SSL transport errors when Ctrl+C is pressed
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # filter SSL cleanup errors from stderr during shutdown
    original_stderr = sys.stderr
    sys.stderr = FilteredStderr(original_stderr)

    try:
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        # cancel all pending tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # give tasks a moment to clean up
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    finally:
        loop.close()
        # restore original stderr
        sys.stderr = original_stderr
