from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from app.models.base import RunScopedModel
from app.models.enums import (
    ArtifactValidationStatus,
    EvidenceRole,
    FindingEvidenceStatus,
    PipelineStage,
    RunAuditEventType,
)
from app.models.validation import TraceabilityCoverage, ValidationResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunAuditEvent(RunScopedModel):
    id: str = Field(min_length=1)
    event_type: RunAuditEventType
    stage: PipelineStage
    message: str = Field(min_length=1)
    artifact_type: Optional[str] = None
    artifact_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TraceabilityMatrixRow(RunScopedModel):
    review_id: Optional[str] = None
    finding_id: Optional[str] = None
    requirement_id: Optional[str] = None
    version: Optional[str] = None
    test_case_id: Optional[str] = None
    evidence_role: Optional[EvidenceRole] = None
    finding_status: Optional[FindingEvidenceStatus] = None
    requirement_validation: Optional[ArtifactValidationStatus] = None
    test_validation: Optional[ArtifactValidationStatus] = None

    @model_validator(mode="after")
    def require_traceable_artifact(self) -> "TraceabilityMatrixRow":
        if not any((self.review_id, self.finding_id, self.requirement_id, self.test_case_id)):
            raise ValueError("A traceability matrix row must reference an artifact.")
        return self


class ForwardTraceability(RunScopedModel):
    review_id: str = Field(min_length=1)
    finding_ids: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)
    test_case_ids: List[str] = Field(default_factory=list)


class ReverseTraceability(RunScopedModel):
    test_case_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    finding_ids: List[str] = Field(default_factory=list)
    review_ids: List[str] = Field(default_factory=list)


class FinalTraceabilityResult(RunScopedModel):
    id: str = Field(min_length=1)
    matrix: List[TraceabilityMatrixRow] = Field(default_factory=list)
    forward: List[ForwardTraceability] = Field(default_factory=list)
    reverse: List[ReverseTraceability] = Field(default_factory=list)
    coverage: TraceabilityCoverage
    validation_results: List[ValidationResult] = Field(default_factory=list)
    unsupported_count: int = Field(default=0, ge=0)
    assumption_count: int = Field(default=0, ge=0)
    revised_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    weak_count: int = Field(default=0, ge=0)
    conflicted_count: int = Field(default=0, ge=0)
    validated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_scope(self) -> "FinalTraceabilityResult":
        scoped = [*self.matrix, *self.forward, *self.reverse, *self.validation_results, self.coverage]
        if any(item.analysis_run_id != self.analysis_run_id for item in scoped):
            raise ValueError("Final traceability artifact belongs to another analysis run.")
        return self


class FinalTraceabilitySummary(RunScopedModel):
    matrix_row_count: int = Field(ge=0)
    overall_traceability_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    hard_failure_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    assumption_count: int = Field(ge=0)
    revised_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    validated_at: datetime


class TraceabilityView(RunScopedModel):
    traceability: Optional[FinalTraceabilityResult] = None
    audit_events: List[RunAuditEvent] = Field(default_factory=list)
