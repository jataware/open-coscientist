"""
Shared utilities for extracting and matching papers_used on hypotheses.

Matches author-year citations in literature_grounding text (e.g. "Roepert et al., 2020")
against candidate paper metadata to determine which papers a hypothesis actually cites.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_author_last_names(authors):
    """Extract last names from an authors list.

    Handles formats like ["John Smith", "J. Smith", "Smith"] by taking
    the last whitespace-delimited token from each entry.
    """
    last_names = []
    for author in authors:
        parts = author.strip().split()
        if parts:
            # last token is typically the last name
            last_names.append(parts[-1].lower().rstrip(".,;"))
    return last_names


def _match_author_year(grounding_lower, last_names, year):
    """Check if any author last name + year pair appears in grounding text."""
    if not year:
        return False
    year_str = str(year)
    if year_str not in grounding_lower:
        return False
    return any(name in grounding_lower for name in last_names if len(name) > 2)


def filter_papers_by_grounding(
    candidates: List[Dict[str, Any]],
    literature_grounding: Optional[str],
) -> List[Dict[str, str]]:
    """Filter candidate papers to only those cited in literature_grounding.

    Matches by checking if an author's last name AND publication year
    both appear in the grounding text (author-year citation style).

    Each candidate dict should have: title, url, authors (list), year (int).

    Returns list of {"title": ..., "url": ...} for matched papers.
    Returns empty list if no grounding text or no matches.
    """
    if not candidates or not literature_grounding:
        return []

    grounding_lower = literature_grounding.lower()
    matched = []
    seen = set()

    for paper in candidates:
        title = paper.get("title", "")
        url = paper.get("url", "")
        authors = paper.get("authors", [])
        year = paper.get("year")

        if not authors:
            continue

        last_names = _extract_author_last_names(authors)
        if _match_author_year(grounding_lower, last_names, year):
            key = (title, url)
            if key not in seen:
                seen.add(key)
                matched.append({"title": title, "url": url})

    if not matched:
        logger.debug(
            f"no author-year matches in literature_grounding "
            f"({len(candidates)} candidates, grounding length={len(literature_grounding)})"
        )

    return matched


def articles_to_candidates(articles):
    """Convert Article objects to candidate dicts for filter_papers_by_grounding."""
    if not articles:
        return []
    return [
        {
            "title": getattr(art, "title", ""),
            "url": getattr(art, "url", "") or "",
            "authors": getattr(art, "authors", []),
            "year": getattr(art, "year", None),
        }
        for art in articles
        if getattr(art, "used_in_analysis", False)
    ]


def analyses_to_candidates(novelty_analyses):
    """Convert novelty analysis paper_metadata to candidate dicts."""
    if not novelty_analyses:
        return []
    candidates = []
    seen = set()
    for analysis in novelty_analyses:
        meta = analysis.get("paper_metadata", {})
        paper_id = meta.get("paper_id", "")
        if paper_id and paper_id not in seen:
            seen.add(paper_id)
            candidates.append({
                "title": meta.get("title", ""),
                "url": paper_id,
                "authors": meta.get("authors", []),
                "year": meta.get("year"),
            })
    return candidates
