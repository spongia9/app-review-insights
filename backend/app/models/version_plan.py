from typing import List, Optional

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


class VersionPlanItem(RunScopedModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    goal: Optional[str] = None
    requirement_ids: List[str]
    validation_result: ArtifactValidationStatus


class VersionPlan(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: Optional[str] = None
    items: List[VersionPlanItem]
    validation_result: ArtifactValidationStatus
