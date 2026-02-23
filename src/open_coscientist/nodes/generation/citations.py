"""
Structured citation utilities for hypothesis generation.

Replaces fragile author-year string matching with explicit citation keys.
All sources use sequential [C*] keys regardless of type — domain-agnostic
and works uniformly for papers, knowledge-graph statements, CVE entries, etc.

Usage:
  1. Build a ReferenceIndex before generation.
  2. Inject reference_index.text into LLM prompts via citation_reference_section.
  3. After the LLM writes literature_grounding, call resolve_citation_keys()
     to build citation_map from the keys it used.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReferenceIndex:
    """Bidirectional map: citation key ↔ full source metadata + prompt text."""

    text: str
    """Formatted reference list for LLM prompt injection, e.g.:
    '[C1] Smith et al., 2023 — Targeted therapies for KRAS...'
    '[C3] INDRA: KRAS → RAF1 [Activation] (belief: 0.95)'
    Empty string when no sources are available.
    """

    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    """key → source dict, e.g. {'C1': {'type': 'paper', 'title': ..., ...}}"""

    def is_empty(self) -> bool:
        return not self.sources


def build_reference_index(
    articles: Optional[List[Any]],
    context_enrichment_sources: Optional[List[Dict[str, Any]]],
) -> ReferenceIndex:
    """Build a sequential reference index from lit-review articles and enrichment sources.

    All sources share a single [C*] key namespace — domain-agnostic.
    Papers come first (they're the primary grounding), enrichment sources follow.
    Only includes articles with used_in_analysis=True.

    Args:
        articles: Article objects from state.articles
        context_enrichment_sources: Structured items from state.context_enrichment_sources

    Returns:
        ReferenceIndex with formatted text and sources dict
    """
    sources: Dict[str, Dict[str, Any]] = {}
    lines: List[str] = []
    counter = 1

    # papers first
    for article in articles or []:
        if not getattr(article, "used_in_analysis", False):
            continue
        key = f"C{counter}"
        title = getattr(article, "title", "") or ""
        url = getattr(article, "url", "") or ""
        authors = getattr(article, "authors", []) or []
        year = getattr(article, "year", None)
        first_author = authors[0].strip().split()[-1] if authors else "Unknown"
        label = f"{first_author} et al., {year}" if year else title[:50]
        lines.append(f"[{key}] {label} — {title[:80]}")
        sources[key] = {
            "type": "paper",
            "title": title,
            "url": url,
            "authors": authors,
            "year": year,
        }
        counter += 1

    # external enrichment sources (e.g. INDRA statements, CVE entries)
    for item in context_enrichment_sources or []:
        key = f"C{counter}"
        display = item.get("display", "External source")
        lines.append(f"[{key}] {display}")
        sources[key] = {
            "type": "knowledge_graph",
            "display": display,
            "tool_id": item.get("tool_id", ""),
            "data": item.get("data", {}),
        }
        counter += 1

    return ReferenceIndex(text="\n".join(lines), sources=sources)


def resolve_citation_keys(
    literature_grounding: Optional[str],
    sources: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Parse [C*] keys from text and resolve them to source metadata.

    Returns a citation_map dict: {key: full source metadata dict}.
    Keys that appear in the text but are absent from sources are silently dropped.
    Preserves insertion order (first occurrence of each key).
    """
    if not literature_grounding or not sources:
        return {}
    keys = re.findall(r"\[C\d+\]", literature_grounding)
    seen: set = set()
    result: Dict[str, Dict[str, Any]] = {}
    for raw_key in keys:
        key = raw_key[1:-1]  # strip brackets → "C1"
        if key in sources and key not in seen:
            result[key] = sources[key]
            seen.add(key)
    return result
