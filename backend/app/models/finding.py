from typing import List, Optional

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import EvidenceStrength, FindingEvidenceStatus


class Finding(RunScopedModel):
    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    title: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    supporting_review_ids: List[str]
    conflicting_review_ids: List[str]
    support_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)

    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_strength: EvidenceStrength
    status: FindingEvidenceStatus
    uncertainty: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
