from datetime import datetime, timezone
from typing import List, Optional

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ValidationResult(RunScopedModel):
    id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    disposition: ArtifactValidationStatus
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    revision_of: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class TraceabilityCoverage(RunScopedModel):
    finding_evidence_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    requirement_traceability_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    test_case_traceability_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    overall_traceability_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    finding_denominator: int = Field(ge=0)
    requirement_denominator: int = Field(ge=0)
    test_case_denominator: int = Field(ge=0)
    hard_failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=utc_now)
