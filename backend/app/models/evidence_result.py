from datetime import datetime
from typing import List

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.evidence import EvidenceValidationAudit
from app.models.finding import Finding


class EvidenceValidationResult(RunScopedModel):
    total_candidate_count: int = Field(ge=0)
    validated_candidate_count: int = Field(ge=0)
    validated_review_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    findings: List[Finding] = Field(default_factory=list)
    audits: List[EvidenceValidationAudit] = Field(default_factory=list)
    validation_time: datetime


class EvidenceValidationSummary(RunScopedModel):
    total_candidate_count: int = Field(ge=0)
    validated_candidate_count: int = Field(ge=0)
    validated_review_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    finding_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    validation_time: datetime


class FindingsView(RunScopedModel):
    findings: List[Finding] = Field(default_factory=list)
    audits: List[EvidenceValidationAudit] = Field(default_factory=list)
