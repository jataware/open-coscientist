# Contributing to Open Coscientist

Thank you for your interest in contributing to Open Coscientist. This document provides guidelines for contributing to the project.

## Development Setup

```bash
git clone https://github.com/jataware/open-coscientist.git
cd open-coscientist

# Use your preferred virtual environment package
python -m venv .venv
source .venv/bin/activate

pip install -e '.[dev]'
```

The rest is similar to installing from pypi- set your LLM API KEY (gemini, openai, anthrophic, etc) and then run your code.

## Code Style

### Comment Formatting

We follow specific conventions for comments to maintain consistency and readability across the codebase.

#### Docstrings

**Always capitalize the first word and use proper punctuation.**

```python
# Good:
def calculate_elo_update(winner_elo: int, loser_elo: int) -> tuple[int, int]:
    """
    Calculate updated Elo ratings for winner and loser.

    Args:
        winner_elo: Current Elo rating of winner
        loser_elo: Current Elo rating of loser

    Returns:
        Tuple of (new_winner_elo, new_loser_elo)
    """
    pass

# Bad:
def calculate_elo_update(winner_elo: int, loser_elo: int) -> tuple[int, int]:
    """
    calculate updated elo ratings for winner and loser
    """
    pass
```

#### Section Comments

**Capitalize major section or block comments** that introduce significant code blocks or logic sections.

```python
# Good:
# Phase 1: try pdf methods first
logger.debug(f"phase 1: attempting pdf extraction")

# Initialize Elo ratings if not already set
for hyp in hypotheses:
    if hyp.elo_rating == INITIAL_ELO_RATING:
        hyp.elo_rating = INITIAL_ELO_RATING

# Bad:
# phase 1: try pdf methods first
# initialize elo ratings if not already set
```

#### Inline Comments

**Keep short inline comments lowercase** unless they're multi-sentence explanations.

```python
max_similarity = 0.0  # track most similar hypothesis
removed_count = 0  # will increment in loop

# Multi-sentence explanatory comments should be capitalized:
# Set deterministic random seed based on research goal and iteration.
# This ensures same inputs produce same tournament pairings for cache consistency.
seed = calculate_seed(research_goal)
```

#### Multi-line Comments

**Capitalize the first line** of multi-line comment blocks.

Example:

```python
# Calculate expected scores using standard Elo formula.
# The expected score represents the probability that a player
# will win based on the rating difference.
expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
```

#### Never Use

- **Emojis** in code comments
- **Unicode decorative characters** (✓, ✗, ⚠️, etc.)

```python
# Bad:
logger.info("✓ Tournament complete")

# Good:
logger.info("Tournament complete")
```

### Logging

We use Python's standard `logging` module with specific conventions for message formatting.

#### Log Level Guidelines

| Level | When to Use | Capitalization |
|-------|-------------|----------------|
| `logger.debug()` | Internal traces, detailed diagnostics | **lowercase** |
| `logger.info()` | User-facing milestones, progress updates | **Capitalize** |
| `logger.warning()` | Recoverable issues, important notices | **Capitalize** |
| `logger.error()` | Errors that affect functionality | **Capitalize** |

#### Examples

```python
# Debug - lowercase, internal details
logger.debug("cache hit for prompt")
logger.debug(f"analyzing hypothesis {i+1}/{len(hypotheses)}")
logger.debug("phase 1: attempting pdf extraction")

# Info - capitalize, user-facing
logger.info("Starting literature review")
logger.info(f"Evolved {len(hypotheses)} hypotheses")
logger.info("Tournament complete")

# Warning - capitalize, important notices
logger.warning("No articles found, skipping reflection")
logger.warning(f"Failed to reach target ({count}/{target})")

# Error - capitalize, serious issues
logger.error("Hypothesis generation failed")
logger.error(f"Reflection failed for hypothesis {i}: {e}")
```

#### What NOT to Include when using logging utilities

- **Emojis**: `logger.info("✓ Done")`
- **Unicode characters**: `logger.info("⚠️ Warning")`
- **Excessive decoration**: `logger.info("*** IMPORTANT ***")`
- **Rich markup**: `logger.info("[green]Success[/green]")`

The Rich library should only be used in `examples/` and `dev/` directories, never in the core library code.

#### Package-Level Logging

We recommend using package-level logging configuration to avoid noise from other libraries:

```python
# Good - configures only open_coscientist logger
import logging
logger = logging.getLogger(__name__)

if verbose:
    logging.getLogger("open_coscientist").setLevel(logging.DEBUG)
else:
    logging.getLogger("open_coscientist").setLevel(logging.INFO)

# Bad - affects all libraries
logging.basicConfig(level=logging.DEBUG)
```

## Questions?

If you have questions about contributing, please open an issue or discussion on GitHub.
