from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from app.models.base import RunScopedModel
from app.models.enums import EvidenceStrength, FindingEvidenceStatus
from app.models.evidence import FindingValidationMetadata


class Finding(RunScopedModel):
    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    title: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    supporting_review_ids: List[str]
    conflicting_review_ids: List[str]
    support_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)

    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_strength: EvidenceStrength
    status: FindingEvidenceStatus
    uncertainty: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    validation_metadata: FindingValidationMetadata

    @field_validator("supporting_review_ids", "conflicting_review_ids")
    @classmethod
    def validate_unique_review_ids(cls, values: List[str]) -> List[str]:
        if len(values) != len(set(values)):
            raise ValueError("Finding Review IDs must be unique.")
        return values

    @model_validator(mode="after")
    def validate_evidence_counts_and_scope(self) -> "Finding":
        if self.support_count != len(self.supporting_review_ids):
            raise ValueError("support_count must equal supporting_review_ids length.")
        if self.conflict_count != len(self.conflicting_review_ids):
            raise ValueError("conflict_count must equal conflicting_review_ids length.")
        if set(self.supporting_review_ids) & set(self.conflicting_review_ids):
            raise ValueError("Supporting and conflicting Review IDs must be disjoint.")
        if self.validation_metadata.analysis_run_id != self.analysis_run_id:
            raise ValueError("Finding validation metadata belongs to another analysis run.")
        return self
