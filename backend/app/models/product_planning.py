from datetime import datetime
from typing import List, Optional

from pydantic import Field, model_validator

from app.models.base import RunScopedModel
from app.models.prd import PRDArtifact, StructuredPRDDraft
from app.models.requirement import Requirement, RequirementDraft
from app.models.test_case import TestCase, TestCaseDraft
from app.models.validation import TraceabilityCoverage, ValidationResult
from app.models.version_plan import VersionPlan, VersionPlanDraft


class ProductPlanningResult(RunScopedModel):
    requirement_drafts: List[RequirementDraft] = Field(default_factory=list)
    requirement_validations: List[ValidationResult] = Field(default_factory=list)
    requirements: List[Requirement] = Field(default_factory=list)
    version_plan_draft: Optional[VersionPlanDraft] = None
    version_plan_validation: Optional[ValidationResult] = None
    version_plan: Optional[VersionPlan] = None
    structured_prd_draft: Optional[StructuredPRDDraft] = None
    prd_validation: Optional[ValidationResult] = None
    prd_artifact: Optional[PRDArtifact] = None
    test_case_drafts: List[TestCaseDraft] = Field(default_factory=list)
    test_case_validations: List[ValidationResult] = Field(default_factory=list)
    test_cases: List[TestCase] = Field(default_factory=list)
    traceability: Optional[TraceabilityCoverage] = None
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    planning_time: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_artifact_scope(self) -> "ProductPlanningResult":
        artifacts = [
            *self.requirement_drafts,
            *self.requirement_validations,
            *self.requirements,
            *self.test_case_drafts,
            *self.test_case_validations,
            *self.test_cases,
        ]
        optional_artifacts = [
            self.version_plan_draft,
            self.version_plan_validation,
            self.version_plan,
            self.structured_prd_draft,
            self.prd_validation,
            self.prd_artifact,
            self.traceability,
        ]
        artifacts.extend(item for item in optional_artifacts if item is not None)
        if any(item.analysis_run_id != self.analysis_run_id for item in artifacts):
            raise ValueError("Product-planning artifact belongs to another analysis run.")
        return self


class ProductPlanningSummary(RunScopedModel):
    requirement_count: int = Field(ge=0)
    rejected_requirement_count: int = Field(ge=0)
    version_count: int = Field(ge=0)
    prd_available: bool
    test_case_count: int = Field(ge=0)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    planning_time: Optional[datetime] = None
    overall_traceability_coverage: Optional[float] = Field(default=None, ge=0, le=1)


class ProductPlanningView(RunScopedModel):
    product_planning: Optional[ProductPlanningResult] = None
