from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.models.base import DomainModel
from app.models.enums import AnalysisOutputLanguage, AnalysisRunStatus, PipelineStage, SourceType


class AnalysisRun(DomainModel):
    id: str = Field(min_length=1)
    source_type: SourceType
    app_id: Optional[str] = None
    analysis_goal: Optional[str] = None
    output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.FOLLOW_UI
    resolved_output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.ZH_CN

    status: AnalysisRunStatus = AnalysisRunStatus.PENDING
    current_stage: PipelineStage = PipelineStage.NOT_STARTED
    last_successful_stage: Optional[PipelineStage] = None
    progress: int = Field(default=0, ge=0, le=100)

    model_provider: Optional[str] = None
    model_name: Optional[str] = None

    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    revisions: List[str] = Field(default_factory=list)

    total_review_count: int = Field(default=0, ge=0)
    analyzed_review_count: int = Field(default=0, ge=0)
    sampling_strategy: Optional[str] = None
    batch_count: int = Field(default=0, ge=0)
    batch_size: int = Field(default=0, ge=0)

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
