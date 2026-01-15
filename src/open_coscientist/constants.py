"""
Constants and configuration values for Open Coscientist.

Centralizes magic numbers and configuration values for better maintainability.
"""

import logging

logger = logging.getLogger(__name__)

# Literature review status markers
LITERATURE_REVIEW_FAILED = "__LIT_REVIEW_FAILED__"
"""Marker indicating literature review failed and should not be used for generation."""

# Elo rating system parameters
INITIAL_ELO_RATING = 1200
"""Initial Elo rating for new hypotheses."""

ELO_K_FACTOR = 24
"""K-factor for Elo rating updates (higher = more volatile ratings)."""

# LLM API parameters
DEFAULT_MAX_TOKENS = 4000
"""Default max tokens for standard LLM calls."""

EXTENDED_MAX_TOKENS = 8000
"""Max tokens for detailed responses (reviews, evolution)."""

LONG_MAX_TOKENS = 10000
"""Max tokens for complex multi-hypothesis operations."""

LITERATURE_REVIEW_MAX_TOKENS = 8000
"""Max tokens for literature review analyses (synthesis outputs)."""

THINKING_MAX_TOKENS = 18000
"""Max tokens for extended thinking + long responses."""

# Temperature settings
LOW_TEMPERATURE = 0.3
"""Low temperature for consistent, deterministic responses (ranking)."""

MEDIUM_TEMPERATURE = 0.5
"""Medium temperature for balanced creativity and consistency."""

HIGH_TEMPERATURE = 0.7
"""Higher temperature for diverse, creative responses (generation, evolution, review)."""

# Review strategy threshold
COMPARATIVE_BATCH_THRESHOLD = 5
"""Maximum hypotheses for comparative batch review. Above this, use parallel individual reviews."""

# Concurrency limits
MAX_CONCURRENT_LLM_CALLS = 5
"""Maximum concurrent LLM API calls to avoid rate limits."""

# Workflow defaults
DEFAULT_MAX_ITERATIONS = 1
"""Default number of refinement iterations."""

# Debate generation parameters
DEBATE_MIN_TURNS = 3
"""Minimum number of debate turns before generating final hypotheses."""

DEBATE_MAX_TURNS = 5
"""Default number of debate turns (can be up to 10)."""

DEFAULT_INITIAL_HYPOTHESES_COUNT = 5
"""Default number of initial hypotheses to generate."""

DEFAULT_EVOLUTION_MAX_COUNT = 3
"""Default number of top hypotheses to evolve and keep."""

# Similarity thresholds
DUPLICATE_SIMILARITY_THRESHOLD = 0.95
"""Similarity threshold above which hypotheses are considered duplicates (0-1)."""

PROXIMITY_SIMILARITY_THRESHOLD = 0.85
"""Similarity threshold for proximity-based deduplication (0-1)."""

# Progress tracking
PROGRESS_SUPERVISOR_START = 5
PROGRESS_SUPERVISOR_COMPLETE = 10
PROGRESS_GENERATE_START = 15
PROGRESS_GENERATE_COMPLETE = 20
PROGRESS_REFLECTION_START = 21
PROGRESS_REFLECTION_COMPLETE = 24
PROGRESS_REVIEW_START = 25
PROGRESS_REVIEW_COMPLETE = 40
PROGRESS_META_REVIEW_START = 45
PROGRESS_META_REVIEW_COMPLETE = 50
PROGRESS_EVOLVE_START = 55
PROGRESS_EVOLVE_COMPLETE = 60
PROGRESS_PROXIMITY_START = 75
PROGRESS_PROXIMITY_COMPLETE = 85

# Cache defaults
DEFAULT_CACHE_DIR = ".coscientist_cache"
"""Default directory for LLM response caching."""

DEFAULT_CACHE_ENABLED = True
"""Whether caching is enabled by default (controls both LLM and node-level caching)."""

LITERATURE_REVIEW_PAPERS_COUNT = 10
"""number of papers to collect from pubmed (configurable via env var)"""

LITERATURE_REVIEW_PAPERS_COUNT_DEV = 4
"""number of papers in dev mode for faster iteration"""

LITERATURE_REVIEW_RECENCY_YEARS = 7
"""filter pubmed papers to last N years for better relevance (0 = no filter)"""

# generate node literature tool usage parameters

def get_draft_max_iterations(hypotheses_count: int) -> int:
    """
    calculate draft iterations based on hypotheses count

    formula: base iterations (for reading papers) + per-hypothesis budget
    - need to read papers: 5 base iterations
    - need to draft each hypothesis: ~2 iterations per hypothesis
    - cap at 30 to prevent runaway

    examples:
    - 3 hypotheses: 5 + 6 = 11 iterations
    - 10 hypotheses: 5 + 20 = 25 iterations
    - 50 hypotheses: 5 + 100 = 30 (capped)
    """
    return min(5 + (hypotheses_count * 2), 30)


def get_validate_max_iterations(hypotheses_count: int) -> int:
    """
    calculate validate iterations based on hypotheses count

    formula: per-hypothesis budget for search + read + refine
    - each hypothesis needs: search (2) + read papers (3-5) + refine (2-3)
    - allow extra for internal iteration (Option B - agent iterates within single call)
    - ~10 iterations per hypothesis
    - cap at 50 to prevent runaway

    examples:
    - 3 hypotheses: 30 iterations
    - 10 hypotheses: 50 (capped)
    - 50 hypotheses: 50 (capped)
    """
    return min(hypotheses_count * 10, 50)


GENERATE_LIT_TOOL_MAX_PAPERS = 3
"""max papers to examine in draft/validate phase.."""
