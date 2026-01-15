"""
Data models for hypothesis generation workflow.

These models maintain compatibility with the original AI-CoScientist
while providing clean type safety for LangGraph.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HypothesisReview:
    """Review of a hypothesis with scores and feedback."""

    review_summary: str
    scores: Dict[str, int]  # scientific_soundness, novelty, relevance, etc.
    safety_ethical_concerns: str
    detailed_feedback: Dict[str, str]
    constructive_feedback: str
    overall_score: float


@dataclass
class Hypothesis:
    """
    A research hypothesis with associated metadata.

    Attributes:
        text: The hypothesis text
        justification: Brief explanation of novelty, significance, and scientific rationale
        literature_review_used: Literature review articles/references used to generate the hypothesis (if applicable)
        novelty_validation: Summary of search queries used to validate novelty and findings (tool-based generation only)
        score: Overall quality score (0-100)
        elo_rating: Elo rating from tournament selection
        reviews: List of reviews received
        similarity_cluster_id: Cluster ID from proximity analysis
        evolution_history: List of refinement summaries
        reflection_notes: Reflection analysis from literature comparison
        generation_method: Method used to generate ('literature' or 'debate')
        debate_id: Debate ID for debate-generated hypotheses (None for literature)
        win_count: Tournament wins
        loss_count: Tournament losses
        total_matches: Total tournament matches
    """

    text: str
    justification: Optional[str] = None
    literature_review_used: Optional[str] = None
    novelty_validation: Optional[str] = None
    score: float = 0.0
    elo_rating: int = 1200  # Starting Elo rating
    reviews: List[HypothesisReview] = field(default_factory=list)
    similarity_cluster_id: Optional[str] = None
    evolution_history: List[str] = field(default_factory=list)
    reflection_notes: Optional[str] = None
    generation_method: Optional[str] = None  # 'literature' or 'debate'
    debate_id: Optional[int] = None  # None for literature-generated, 0-N for debate-generated
    win_count: int = 0
    loss_count: int = 0

    @property
    def total_matches(self) -> int:
        """Total tournament matches played."""
        return self.win_count + self.loss_count

    @property
    def win_rate(self) -> float:
        """Win rate percentage (0-100)."""
        if self.total_matches == 0:
            return 0.0
        return (self.win_count / self.total_matches) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "justification": self.justification,
            "literature_review_used": self.literature_review_used,
            "novelty_validation": self.novelty_validation,
            "score": self.score,
            "elo_rating": self.elo_rating,
            "reviews": [
                {
                    "review_summary": r.review_summary,
                    "scores": r.scores,
                    "safety_ethical_concerns": r.safety_ethical_concerns,
                    "detailed_feedback": r.detailed_feedback,
                    "constructive_feedback": r.constructive_feedback,
                    "overall_score": r.overall_score,
                }
                for r in self.reviews
            ],
            "similarity_cluster_id": self.similarity_cluster_id,
            "evolution_history": self.evolution_history,
            "reflection_notes": self.reflection_notes,
            "generation_method": self.generation_method,
            "debate_id": self.debate_id,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "total_matches": self.total_matches,
            "win_rate": self.win_rate,
        }


@dataclass
class ExecutionMetrics:
    """Metrics for workflow execution."""

    total_time: float = 0.0
    hypothesis_count: int = 0
    reviews_count: int = 0
    tournaments_count: int = 0
    evolutions_count: int = 0
    llm_calls: int = 0  # Total LLM calls made
    phase_times: Dict[str, float] = field(default_factory=dict)


def create_metrics_update(
    hypothesis_count: Optional[int] = None,
    reviews_count_delta: int = 0,
    tournaments_count_delta: int = 0,
    evolutions_count_delta: int = 0,
    llm_calls_delta: int = 0,
    total_time: Optional[float] = None,
    phase_times: Optional[Dict[str, float]] = None,
) -> ExecutionMetrics:
    """
    create new ExecutionMetrics with ONLY the deltas (not cumulative).

    the merge_metrics reducer will add these deltas to the existing state.
    do NOT pass base metrics - only pass the increments from this node.

    Args:
        hypothesis_count: new total hypothesis count (replaces via max(), not adds)
        reviews_count_delta: number of reviews to add (delta only)
        tournaments_count_delta: number of tournaments to add (delta only)
        evolutions_count_delta: number of evolutions to add (delta only)
        llm_calls_delta: number of llm calls to add (delta only)
        total_time: new total time (only set if > 0)
        phase_times: new phase times dict (merged with existing)

    Returns:
        new ExecutionMetrics object with ONLY deltas
    """
    return ExecutionMetrics(
        hypothesis_count=hypothesis_count if hypothesis_count is not None else 0,
        reviews_count=reviews_count_delta,
        tournaments_count=tournaments_count_delta,
        evolutions_count=evolutions_count_delta,
        llm_calls=llm_calls_delta,
        total_time=total_time if total_time is not None else 0.0,
        phase_times=phase_times if phase_times is not None else {},
    )


@dataclass
class Article:
    """
    A literature article with extracted content and metadata.

    Note: In PubMed-only mode, `content` and `pdf_links` are unused.
    Fulltext content is accessed directly by PaperQA from HTML files.
    """

    title: str
    url: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    citations: int = 0
    abstract: Optional[str] = None
    content: Optional[str] = None  # unused in PubMed-only mode (PaperQA reads HTML files directly)
    source_id: Optional[str] = None
    source: str = "pubmed"  # default changed to "pubmed" (was "google_scholar")
    pdf_links: List[str] = field(default_factory=list)  # unused in PubMed-only mode (HTML-only)
    used_in_analysis: bool = False  # flag indicating if this article was analyzed by the agent

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
