from datetime import datetime
from typing import List

from pydantic import Field, field_validator, model_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import EvidenceStance, EvidenceStrength, FindingEvidenceStatus


def _unique_ids(values: List[str]) -> List[str]:
    if len(values) != len(set(values)):
        raise ValueError("Review identifiers must be unique.")
    return values


class EvidenceJudgment(RunScopedModel):
    finding_candidate_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    stance: EvidenceStance
    semantic_relevance: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class EvidenceJudgmentOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    finding_candidate_id: str = Field(min_length=1)
    judgments: List[EvidenceJudgment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope_and_ids(self) -> "EvidenceJudgmentOutput":
        review_ids = [judgment.review_id for judgment in self.judgments]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("Evidence judgments must contain unique Review IDs.")
        for judgment in self.judgments:
            if judgment.analysis_run_id != self.analysis_run_id:
                raise ValueError("Evidence judgment belongs to another analysis run.")
            if judgment.finding_candidate_id != self.finding_candidate_id:
                raise ValueError("Evidence judgment belongs to another Finding Candidate.")
        return self

class EvidenceValidationBatch(RunScopedModel):
    id: str = Field(min_length=1)
    finding_candidate_id: str = Field(min_length=1)
    review_ids: List[str] = Field(min_length=1)
    judgments: List[EvidenceJudgment] = Field(min_length=1)

    _validate_review_ids = field_validator("review_ids")(_unique_ids)

    @model_validator(mode="after")
    def validate_judgment_coverage(self) -> "EvidenceValidationBatch":
        judged_ids = [judgment.review_id for judgment in self.judgments]
        if set(judged_ids) != set(self.review_ids) or len(judged_ids) != len(self.review_ids):
            raise ValueError("Evidence batch judgments must exactly cover the batch Review IDs.")
        return self


class EvidenceMetrics(DomainModel):
    validated_review_count: int = Field(ge=0)
    relevant_review_count: int = Field(ge=0)
    support_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    irrelevant_count: int = Field(ge=0)
    support_ratio: float = Field(ge=0, le=1)
    conflict_ratio: float = Field(ge=0, le=1)
    evidence_density: float = Field(ge=0, le=1)
    average_support_relevance: float = Field(ge=0, le=1)


class FindingValidationMetadata(RunScopedModel):
    audit_id: str = Field(min_length=1)
    finding_candidate_id: str = Field(min_length=1)
    metrics: EvidenceMetrics
    validated_review_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    eligible_for_requirement_generation: bool = False
    validation_time: datetime


class EvidenceValidationAudit(RunScopedModel):
    id: str = Field(min_length=1)
    finding_candidate_id: str = Field(min_length=1)
    candidate_review_ids: List[str]
    validation_review_ids: List[str]
    supporting_review_ids: List[str]
    conflicting_review_ids: List[str]
    neutral_review_ids: List[str]
    irrelevant_review_ids: List[str]
    judgments: List[EvidenceJudgment]
    validation_batches: List[EvidenceValidationBatch]
    status: FindingEvidenceStatus
    confidence: float = Field(ge=0, le=1)
    evidence_strength: EvidenceStrength
    metrics: EvidenceMetrics
    uncertainty: str = Field(min_length=1)
    limitations: List[str]
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    validation_time: datetime
    revisions: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    _validate_candidate_ids = field_validator("candidate_review_ids")(_unique_ids)
    _validate_validation_ids = field_validator("validation_review_ids")(_unique_ids)
    _validate_support_ids = field_validator("supporting_review_ids")(_unique_ids)
    _validate_conflict_ids = field_validator("conflicting_review_ids")(_unique_ids)
    _validate_neutral_ids = field_validator("neutral_review_ids")(_unique_ids)
    _validate_irrelevant_ids = field_validator("irrelevant_review_ids")(_unique_ids)

    @model_validator(mode="after")
    def validate_partitions(self) -> "EvidenceValidationAudit":
        partitions = [
            set(self.supporting_review_ids),
            set(self.conflicting_review_ids),
            set(self.neutral_review_ids),
            set(self.irrelevant_review_ids),
        ]
        if any(partitions[left] & partitions[right] for left in range(4) for right in range(left + 1, 4)):
            raise ValueError("Evidence stance partitions must be disjoint.")
        if set().union(*partitions) != set(self.validation_review_ids):
            raise ValueError("Evidence stance partitions must cover every validated Review ID.")
        return self
