from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.ingestion import CleaningStatistics, RejectedReview
from app.models.review import Review


@dataclass(frozen=True)
class ReviewCandidate:
    source: str
    raw_data: Dict[str, Any]
    source_review_id: Optional[Any] = None
    app_id: Optional[Any] = None
    author: Optional[Any] = None
    rating: Optional[Any] = None
    title: Optional[Any] = None
    text: Optional[Any] = None
    version: Optional[Any] = None
    language: Optional[Any] = None
    created_at: Optional[Any] = None
    storefront: Optional[Any] = None


@dataclass(frozen=True)
class ProviderBatch:
    source: str
    collection_time: datetime
    candidates: List[ReviewCandidate]
    raw_review_count: int
    storefront: Optional[str] = None
    app_id: Optional[str] = None
    source_limitations: List[str] = field(default_factory=list)
    rejected_rows: List[RejectedReview] = field(default_factory=list)
    is_live_collection: bool = False
    storefront_verified: bool = False


@dataclass(frozen=True)
class ProviderResult:
    batch: ProviderBatch
    reviews: List[Review]
    statistics: CleaningStatistics
    rejected_rows: List[RejectedReview]


class ReviewProvider(ABC):
    @abstractmethod
    def load(self) -> ProviderBatch:
        """Load source records into the source-neutral candidate contract."""

    def provide(self, analysis_run_id: str) -> ProviderResult:
        """Return final run-scoped Reviews through the shared deterministic cleaner."""
        from app.cleaning import clean_reviews

        batch = self.load()
        reviews, statistics, rejected_rows = clean_reviews(
            batch,
            analysis_run_id=analysis_run_id,
        )
        return ProviderResult(
            batch=batch,
            reviews=reviews,
            statistics=statistics,
            rejected_rows=rejected_rows,
        )

    def get_reviews(self, analysis_run_id: str) -> List[Review]:
        """Convenience form of the provider contract returning only unified Reviews."""
        return self.provide(analysis_run_id).reviews
