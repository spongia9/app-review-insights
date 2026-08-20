from datetime import datetime
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import (
    ArtifactValidationStatus,
    ImpactLevel,
    RequirementGroundingVerdict,
    RequirementPriority,
)


def _unique_non_empty_ids(values: List[str]) -> List[str]:
    if not values:
        raise ValueError("At least one identifier is required.")
    if len(values) != len(set(values)):
        raise ValueError("Identifiers must be unique.")
    return values


def _unique_non_empty_text(values: List[str]) -> List[str]:
    normalized = [value.strip() for value in values]
    if not normalized or any(not value for value in normalized):
        raise ValueError("At least one non-empty text item is required.")
    if len(normalized) != len(set(normalized)):
        raise ValueError("Text items must be unique.")
    return normalized


class RequirementProposal(DomainModel):
    title: str = Field(min_length=1)
    user_problem: str = Field(min_length=1)
    description: str = Field(min_length=1)
    finding_ids: List[str] = Field(min_length=1)
    proposed_priority: RequirementPriority
    impact: ImpactLevel
    acceptance_criteria: List[str] = Field(min_length=1)
    target_version: Optional[str] = None
    assumption: bool = False

    _validate_finding_ids = field_validator("finding_ids")(_unique_non_empty_ids)
    _validate_acceptance_criteria = field_validator("acceptance_criteria")(
        _unique_non_empty_text
    )


class RequirementDraft(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    user_problem: str = Field(min_length=1)
    description: str = Field(min_length=1)
    finding_ids: List[str] = Field(min_length=1)
    proposed_priority: RequirementPriority
    impact: ImpactLevel
    acceptance_criteria: List[str] = Field(min_length=1)
    target_version: Optional[str] = None
    assumption: bool = False
    generated_at: datetime

    _validate_finding_ids = field_validator("finding_ids")(_unique_non_empty_ids)
    _validate_acceptance_criteria = field_validator("acceptance_criteria")(
        _unique_non_empty_text
    )


class RequirementDraftOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    requirements: List[RequirementProposal] = Field(min_length=1)


class RequirementGroundingDecision(RunScopedModel):
    requirement_draft_id: str = Field(min_length=1)
    verdict: RequirementGroundingVerdict
    reason: str = Field(min_length=1)
    acceptance_criteria_testable: bool
    revised_title: Optional[str] = None
    revised_user_problem: Optional[str] = None
    revised_description: Optional[str] = None
    revised_acceptance_criteria: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_revision(self) -> "RequirementGroundingDecision":
        needs_revision = self.verdict == RequirementGroundingVerdict.PARTIAL or (
            self.verdict == RequirementGroundingVerdict.GROUNDED
            and not self.acceptance_criteria_testable
        )
        revision_fields = (
            self.revised_title,
            self.revised_user_problem,
            self.revised_description,
            self.revised_acceptance_criteria,
        )
        if needs_revision and not all(revision_fields):
            raise ValueError("A partial or untestable Requirement needs a complete revision.")
        if self.revised_acceptance_criteria is not None:
            _unique_non_empty_text(self.revised_acceptance_criteria)
        return self


class RequirementGroundingOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    decisions: List[RequirementGroundingDecision] = Field(min_length=1)


class RequirementGenerationMetadata(RunScopedModel):
    draft_id: str = Field(min_length=1)
    validation_id: str = Field(min_length=1)
    grounding_verdict: RequirementGroundingVerdict
    generated_by: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    generated_at: datetime
    priority_adjusted: bool = False


class Requirement(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    user_problem: str = Field(min_length=1)
    description: str = Field(min_length=1)

    finding_ids: List[str] = Field(min_length=1)
    review_ids: List[str] = Field(min_length=1)

    priority: RequirementPriority
    recommended_priority: RequirementPriority
    final_priority: RequirementPriority
    priority_reason: str = Field(min_length=1)
    impact: ImpactLevel
    confidence: float = Field(ge=0, le=1)
    acceptance_criteria: List[str] = Field(min_length=1)
    target_version: Optional[str] = None
    assumption: bool = False
    validation_result: ArtifactValidationStatus
    generated_by: str = Field(min_length=1)
    generation_metadata: RequirementGenerationMetadata

    _validate_finding_ids = field_validator("finding_ids")(_unique_non_empty_ids)
    _validate_review_ids = field_validator("review_ids")(_unique_non_empty_ids)
    _validate_acceptance_criteria = field_validator("acceptance_criteria")(
        _unique_non_empty_text
    )

    @model_validator(mode="after")
    def validate_final_priority_and_scope(self) -> "Requirement":
        if self.priority != self.final_priority:
            raise ValueError("priority must equal final_priority.")
        if self.generation_metadata.analysis_run_id != self.analysis_run_id:
            raise ValueError("Requirement generation metadata belongs to another run.")
        if self.generated_by != self.generation_metadata.generated_by:
            raise ValueError("generated_by must match generation metadata.")
        return self
