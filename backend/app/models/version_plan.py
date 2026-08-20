from datetime import datetime
from typing import List

from pydantic import Field, field_validator, model_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import ArtifactValidationStatus


def _unique_requirement_ids(values: List[str]) -> List[str]:
    if not values:
        raise ValueError("A VersionPlan item must include at least one Requirement.")
    if len(values) != len(set(values)):
        raise ValueError("VersionPlan Requirement IDs must be unique within an item.")
    return values


class VersionPlanItemProposal(DomainModel):
    version: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    requirement_ids: List[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    dependencies: List[str] = Field(default_factory=list)
    risk: str = Field(min_length=1)
    scope_note: str = Field(min_length=1)

    _validate_requirement_ids = field_validator("requirement_ids")(_unique_requirement_ids)


class VersionPlanDraft(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    items: List[VersionPlanItemProposal] = Field(min_length=1)
    generated_at: datetime


class VersionPlanDraftOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    items: List[VersionPlanItemProposal] = Field(min_length=1)


class VersionPlanItem(RunScopedModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    requirement_ids: List[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    dependencies: List[str] = Field(default_factory=list)
    risk: str = Field(min_length=1)
    scope_note: str = Field(min_length=1)
    validation_result: ArtifactValidationStatus

    _validate_requirement_ids = field_validator("requirement_ids")(_unique_requirement_ids)


class VersionPlan(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    items: List[VersionPlanItem] = Field(min_length=1)
    validation_result: ArtifactValidationStatus
    generated_by: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_item_scope_and_assignment(self) -> "VersionPlan":
        requirement_ids: List[str] = []
        for item in self.items:
            if item.analysis_run_id != self.analysis_run_id:
                raise ValueError("VersionPlan item belongs to another analysis run.")
            requirement_ids.extend(item.requirement_ids)
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("A Requirement cannot be assigned to multiple VersionPlan items.")
        return self
