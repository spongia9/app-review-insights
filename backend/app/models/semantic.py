from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.models.base import DomainModel, RunScopedModel
from app.models.enums import (
    AnalysisOutputLanguage,
    AuditArtifactType,
    CandidateStatus,
    PipelineStage,
)


def _unique_nonempty(values: List[str]) -> List[str]:
    if len(values) != len(set(values)):
        raise ValueError("Identifiers must be unique.")
    return values


class TopicCandidate(RunScopedModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    review_ids: List[str] = Field(min_length=1)
    batch_id: str = Field(min_length=1)

    _validate_review_ids = field_validator("review_ids")(_unique_nonempty)


class FindingCandidate(RunScopedModel):
    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    title: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supporting_review_ids: List[str] = Field(min_length=1)
    source_batch_ids: List[str] = Field(min_length=1)
    candidate_status: CandidateStatus = CandidateStatus.UNVALIDATED_CANDIDATE

    _validate_review_ids = field_validator("supporting_review_ids")(_unique_nonempty)
    _validate_batch_ids = field_validator("source_batch_ids")(_unique_nonempty)


class TopicDiscoveryOutput(DomainModel):
    topics: List[TopicCandidate] = Field(default_factory=list)


class FindingCandidateOutput(DomainModel):
    finding_candidates: List[FindingCandidate] = Field(default_factory=list)


class BatchAnalysisResult(RunScopedModel):
    batch_id: str = Field(min_length=1)
    review_ids: List[str] = Field(min_length=1)
    topic_candidates: List[TopicCandidate] = Field(default_factory=list)
    finding_candidates: List[FindingCandidate] = Field(default_factory=list)

    _validate_review_ids = field_validator("review_ids")(_unique_nonempty)


class ConsolidatedAnalysisResult(RunScopedModel):
    topic_candidates: List[TopicCandidate] = Field(default_factory=list)
    finding_candidates: List[FindingCandidate] = Field(default_factory=list)


class AuditArtifact(RunScopedModel):
    id: str = Field(min_length=1)
    artifact_type: AuditArtifactType
    stage: PipelineStage
    batch_id: Optional[str] = None
    payload: Dict[str, Any]
    created_at: datetime


class SemanticAnalysisResult(RunScopedModel):
    total_review_count: int = Field(ge=0)
    analyzed_review_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    sampling_strategy: str = "NONE"
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    analysis_goal: Optional[str] = None
    output_language: AnalysisOutputLanguage
    resolved_output_language: AnalysisOutputLanguage
    batch_results: List[BatchAnalysisResult] = Field(default_factory=list)
    consolidated_result: Optional[ConsolidatedAnalysisResult] = None
    audit_artifacts: List[AuditArtifact] = Field(default_factory=list)
    analysis_time: Optional[datetime] = None


class SemanticAnalysisSummary(RunScopedModel):
    total_review_count: int = Field(ge=0)
    analyzed_review_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    sampling_strategy: str
    model_provider: str
    model_name: str
    analysis_goal: Optional[str] = None
    output_language: AnalysisOutputLanguage
    resolved_output_language: AnalysisOutputLanguage
    topic_count: int = Field(ge=0)
    finding_candidate_count: int = Field(ge=0)
    analysis_time: Optional[datetime] = None


class TopicsView(RunScopedModel):
    topics: List[TopicCandidate] = Field(default_factory=list)


class FindingCandidatesView(RunScopedModel):
    finding_candidates: List[FindingCandidate] = Field(default_factory=list)
