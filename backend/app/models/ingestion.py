from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.models.analysis_run import AnalysisRun
from app.models.base import DomainModel, RunScopedModel
from app.models.review import Review
from app.models.semantic import SemanticAnalysisResult, SemanticAnalysisSummary
from app.models.evidence_result import EvidenceValidationResult, EvidenceValidationSummary
from app.models.product_planning import ProductPlanningResult, ProductPlanningSummary
from app.models.traceability import (
    FinalTraceabilityResult,
    FinalTraceabilitySummary,
    RunAuditEvent,
)


class RejectedReview(DomainModel):
    row_number: int = Field(ge=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ProviderMetadata(RunScopedModel):
    source: str = Field(min_length=1)
    storefront: Optional[str] = None
    collection_time: datetime
    source_limitations: List[str] = Field(default_factory=list)
    is_live_collection: bool = False
    storefront_verified: bool = False


class CleaningStatistics(RunScopedModel):
    raw_review_count: int = Field(ge=0)
    clean_review_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    empty_count: int = Field(ge=0)
    retention_rate: float = Field(ge=0, le=1)


class IngestionResult(RunScopedModel):
    run: AnalysisRun
    provider: ProviderMetadata
    statistics: Optional[CleaningStatistics] = None
    reviews: List[Review] = Field(default_factory=list)
    rejected_rows: List[RejectedReview] = Field(default_factory=list)
    semantic_analysis: Optional[SemanticAnalysisResult] = None
    evidence_validation: Optional[EvidenceValidationResult] = None
    product_planning: Optional[ProductPlanningResult] = None
    final_traceability: Optional[FinalTraceabilityResult] = None
    audit_events: List[RunAuditEvent] = Field(default_factory=list)


class AnalysisRunView(RunScopedModel):
    run: AnalysisRun
    provider: ProviderMetadata
    statistics: Optional[CleaningStatistics] = None
    semantic_analysis: Optional[SemanticAnalysisSummary] = None
    evidence_validation: Optional[EvidenceValidationSummary] = None
    product_planning: Optional[ProductPlanningSummary] = None
    final_traceability: Optional[FinalTraceabilitySummary] = None
    audit_event_count: int = Field(default=0, ge=0)


class ReviewsView(RunScopedModel):
    reviews: List[Review] = Field(default_factory=list)
