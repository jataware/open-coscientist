"""
Hypothesis generation strategies - modular and composable.

Exports the main coordinator function for use by the generate node.
"""

from .coordinator import generate_hypotheses

__all__ = ["generate_hypotheses"]
