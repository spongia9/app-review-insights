from datetime import datetime
from typing import List

from pydantic import Field, field_validator, model_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import ArtifactValidationStatus


def _unique_ids(values: List[str]) -> List[str]:
    if len(values) != len(set(values)):
        raise ValueError("PRD references must be unique.")
    return values


class PRDSectionProposal(DomainModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    finding_ids: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)
    version_item_ids: List[str] = Field(default_factory=list)
    assumption: bool = False

    _validate_finding_ids = field_validator("finding_ids")(_unique_ids)
    _validate_requirement_ids = field_validator("requirement_ids")(_unique_ids)
    _validate_version_ids = field_validator("version_item_ids")(_unique_ids)


class StructuredPRDDraft(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    product_goal: str = Field(min_length=1)
    background: str = Field(min_length=1)
    analysis_scope: str = Field(min_length=1)
    user_problems: List[PRDSectionProposal] = Field(min_length=1)
    findings_summary: List[PRDSectionProposal] = Field(min_length=1)
    requirements: List[PRDSectionProposal] = Field(min_length=1)
    release_plan: List[PRDSectionProposal] = Field(min_length=1)
    acceptance_criteria: List[PRDSectionProposal] = Field(min_length=1)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    version_plan_id: str = Field(min_length=1)
    generated_at: datetime


class StructuredPRDDraftOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    product_goal: str = Field(min_length=1)
    background: str = Field(min_length=1)
    analysis_scope: str = Field(min_length=1)
    user_problems: List[PRDSectionProposal] = Field(min_length=1)
    findings_summary: List[PRDSectionProposal] = Field(min_length=1)
    requirements: List[PRDSectionProposal] = Field(min_length=1)
    release_plan: List[PRDSectionProposal] = Field(min_length=1)
    acceptance_criteria: List[PRDSectionProposal] = Field(min_length=1)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    version_plan_id: str = Field(min_length=1)


class PRDSection(RunScopedModel):
    id: str = Field(min_length=1)
    section_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    finding_ids: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)
    version_item_ids: List[str] = Field(default_factory=list)
    assumption: bool = False
    validation_result: ArtifactValidationStatus

    _validate_finding_ids = field_validator("finding_ids")(_unique_ids)
    _validate_requirement_ids = field_validator("requirement_ids")(_unique_ids)
    _validate_version_ids = field_validator("version_item_ids")(_unique_ids)


class StructuredPRD(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    product_goal: str = Field(min_length=1)
    background: str = Field(min_length=1)
    analysis_scope: str = Field(min_length=1)
    user_problems: List[PRDSection] = Field(min_length=1)
    findings_summary: List[PRDSection] = Field(min_length=1)
    requirements: List[PRDSection] = Field(min_length=1)
    release_plan: List[PRDSection] = Field(min_length=1)
    acceptance_criteria: List[PRDSection] = Field(min_length=1)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    evidence_summary: PRDSection
    version_plan_id: str = Field(min_length=1)
    validation_result: ArtifactValidationStatus

    @model_validator(mode="after")
    def validate_section_scope(self) -> "StructuredPRD":
        sections = [
            *self.user_problems,
            *self.findings_summary,
            *self.requirements,
            *self.release_plan,
            *self.acceptance_criteria,
            self.evidence_summary,
        ]
        if any(section.analysis_run_id != self.analysis_run_id for section in sections):
            raise ValueError("PRD section belongs to another analysis run.")
        return self


class PRDArtifact(RunScopedModel):
    id: str = Field(min_length=1)
    structured_prd: StructuredPRD
    rendered_markdown: str = Field(min_length=1)
    validation_result: ArtifactValidationStatus
    generated_by: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_prd_scope(self) -> "PRDArtifact":
        if self.structured_prd.analysis_run_id != self.analysis_run_id:
            raise ValueError("Structured PRD belongs to another analysis run.")
        return self
