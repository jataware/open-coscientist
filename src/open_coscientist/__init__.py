"""
Open Coscientist: AI Co-Scientist framework reimplemented with LangGraph.

This package provides a clean, modular implementation of the AI Co-Scientist
framework using LangGraph for workflow orchestration.

Key features:
- Drop-in replacement for the original AI-CoScientist
- Prompts stored as markdown files for easy modification
- Parallel execution of reviews and evolution
- Native LangSmith integration for observability
- Clean separation of concerns with typed state management

Example usage:
    >>> from open_coscientist import HypothesisGenerator
    >>>
    >>> generator = HypothesisGenerator(
    ...     model_name="gemini/gemini-2.5-flash",
    ...     max_iterations=1,
    ...     initial_hypotheses_count=5,
    ...     evolution_max_count=3
    ... )
    >>>
    >>> result = await generator.generate_hypotheses(
    ...     research_goal="Develop novel approaches for early cancer detection",
    ...     progress_callback=lambda phase, data: print(f"{phase}: {data}")
    ... )
    >>>
    >>> for hyp in result["hypotheses"]:
    ...     print(f"- {hyp['text']} (score: {hyp['score']})")
"""

import sys

# ensure Python version compatibility
if sys.version_info < (3, 10):
    raise RuntimeError(
        "Open Coscientist requires Python >= 3.10. "
        "Please upgrade to Python 3.10 or newer."
    )

from .generator import HypothesisGenerator
from .models import Hypothesis, HypothesisReview, ExecutionMetrics
from .state import WorkflowState, WorkflowConfig
from .cache import clear_cache, get_cache_stats, clear_node_cache, get_node_cache_stats
from .console import ConsoleReporter

__version__ = "0.1.0"
__all__ = [
    "HypothesisGenerator",
    "Hypothesis",
    "HypothesisReview",
    "ExecutionMetrics",
    "WorkflowState",
    "WorkflowConfig",
    "ConsoleReporter",
    "clear_cache",
    "get_cache_stats",
    "clear_node_cache",
    "get_node_cache_stats",
]
