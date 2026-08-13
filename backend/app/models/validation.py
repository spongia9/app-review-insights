from datetime import datetime, timezone
from typing import List, Optional

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ValidationResult(RunScopedModel):
    id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    disposition: ArtifactValidationStatus
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    revision_of: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
