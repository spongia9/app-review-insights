from typing import List

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


class TestCase(RunScopedModel):
    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    source_review_ids: List[str]

    title: str = Field(min_length=1)
    preconditions: List[str]
    steps: List[str]
    expected_result: str = Field(min_length=1)
    test_type: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    validation_result: ArtifactValidationStatus
