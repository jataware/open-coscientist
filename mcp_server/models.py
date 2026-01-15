"""
Data models for literature review tools.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Article:
    """A literature article with extracted content and metadata."""

    title: str
    url: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    citations: int = 0
    abstract: Optional[str] = None
    content: Optional[str] = None
    source_id: Optional[str] = None
    source: str = "google_scholar"
    pdf_links: List[str] = field(default_factory=list)
    used_in_analysis: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "url": self.url,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "citations": self.citations,
            "abstract": self.abstract,
            "content": self.content,
            "source_id": self.source_id,
            "source": self.source,
            "pdf_links": self.pdf_links,
            "used_in_analysis": self.used_in_analysis,
        }
