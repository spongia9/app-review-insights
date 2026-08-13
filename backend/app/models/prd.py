from typing import List

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


class PRDSection(RunScopedModel):
    id: str = Field(min_length=1)
    section_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    finding_ids: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)
    assumption: bool = False
    validation_result: ArtifactValidationStatus


class StructuredPRD(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    product_goal: str = Field(min_length=1)
    sections: List[PRDSection]
    version_plan_id: str = Field(min_length=1)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    validation_result: ArtifactValidationStatus
