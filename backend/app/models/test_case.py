from datetime import datetime
from typing import List

from pydantic import Field, field_validator, model_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import ArtifactValidationStatus, RequirementPriority, TestCaseType
from app.models.requirement import _unique_non_empty_text


class TestCaseProposal(DomainModel):
    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    preconditions: List[str] = Field(min_length=1)
    steps: List[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    test_type: TestCaseType
    proposed_priority: RequirementPriority

    _validate_preconditions = field_validator("preconditions")(_unique_non_empty_text)
    _validate_steps = field_validator("steps")(_unique_non_empty_text)


class TestCaseDraft(RunScopedModel):
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    preconditions: List[str] = Field(min_length=1)
    steps: List[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    test_type: TestCaseType
    proposed_priority: RequirementPriority
    generated_at: datetime

    _validate_preconditions = field_validator("preconditions")(_unique_non_empty_text)
    _validate_steps = field_validator("steps")(_unique_non_empty_text)


class TestCaseDraftOutput(DomainModel):
    analysis_run_id: str = Field(min_length=1)
    test_cases: List[TestCaseProposal] = Field(min_length=1)


class TestCase(RunScopedModel):
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    source_review_ids: List[str] = Field(min_length=1)
    title: str = Field(min_length=1)
    preconditions: List[str] = Field(min_length=1)
    steps: List[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    test_type: TestCaseType
    priority: RequirementPriority
    validation_result: ArtifactValidationStatus
    generated_by: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    generated_at: datetime
    draft_id: str = Field(min_length=1)

    _validate_source_review_ids = field_validator("source_review_ids")(
        lambda values: _unique_non_empty_text(values)
    )
    _validate_preconditions = field_validator("preconditions")(_unique_non_empty_text)
    _validate_steps = field_validator("steps")(_unique_non_empty_text)

    @model_validator(mode="after")
    def validate_step_quality(self) -> "TestCase":
        if len(self.steps) < 2:
            raise ValueError("A TestCase must include at least two observable steps.")
        return self
