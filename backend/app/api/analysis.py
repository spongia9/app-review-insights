from threading import Thread
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.models import (
    AnalysisOutputLanguage,
    AnalysisRunView,
    FindingsView,
    FindingCandidatesView,
    IngestionResult,
    ReviewsView,
    TopicsView,
)
from app.providers.errors import IngestionError
from app.services import (
    EvidenceValidationError,
    EvidenceValidationService,
    IngestionService,
    SemanticAnalysisError,
    SemanticAnalysisService,
)
from app.services.evidence import evidence_summary
from app.services.semantic import semantic_summary
from app.storage import RunStore


router = APIRouter(prefix="/analysis", tags=["analysis"])


class AppStoreAnalysisRequest(BaseModel):
    app_store_url: str = Field(min_length=1)
    analysis_goal: Optional[str] = None
    output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.FOLLOW_UI


class SemanticAnalysisRequest(BaseModel):
    output_language: Optional[AnalysisOutputLanguage] = None
    ui_language: Optional[str] = Field(default=None, pattern="^(zh-CN|en-US)$")


class EvidenceValidationRequest(BaseModel):
    candidate_ids: Optional[List[str]] = None


def get_service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


def get_semantic_service(request: Request) -> SemanticAnalysisService:
    return request.app.state.semantic_analysis_service


def get_evidence_service(request: Request) -> EvidenceValidationService:
    return request.app.state.evidence_validation_service


def raise_http_error(error: IngestionError) -> None:
    detail: Dict[str, Any] = {
        "code": error.code,
        "message": error.message,
        **error.details,
    }
    raise HTTPException(status_code=error.status_code, detail=detail) from error


@router.post("/app-store", response_model=IngestionResult)
def create_app_store_run(
    payload: AppStoreAnalysisRequest,
    request: Request,
) -> IngestionResult:
    try:
        return get_service(request).ingest_app_store(
            payload.app_store_url,
            payload.analysis_goal,
            payload.output_language,
        )
    except IngestionError as error:
        raise_http_error(error)


@router.post("/import/csv", response_model=IngestionResult)
async def create_csv_run(
    request: Request,
    file: UploadFile = File(...),
    analysis_goal: Optional[str] = Form(default=None),
    output_language: AnalysisOutputLanguage = Form(default=AnalysisOutputLanguage.FOLLOW_UI),
) -> IngestionResult:
    try:
        data = await file.read(get_service(request).settings.max_upload_bytes + 1)
        return get_service(request).ingest_csv(data, analysis_goal, output_language)
    except IngestionError as error:
        raise_http_error(error)


@router.post("/import/json", response_model=IngestionResult)
async def create_json_run(
    request: Request,
    file: UploadFile = File(...),
    analysis_goal: Optional[str] = Form(default=None),
    output_language: AnalysisOutputLanguage = Form(default=AnalysisOutputLanguage.FOLLOW_UI),
) -> IngestionResult:
    try:
        data = await file.read(get_service(request).settings.max_upload_bytes + 1)
        return get_service(request).ingest_json(data, analysis_goal, output_language)
    except IngestionError as error:
        raise_http_error(error)


def require_result(analysis_run_id: str, request: Request) -> IngestionResult:
    result = get_store(request).get(analysis_run_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RUN_NOT_FOUND", "message": "Analysis run was not found."},
        )
    return result


@router.get("/{analysis_run_id}", response_model=AnalysisRunView)
def get_analysis_run(analysis_run_id: str, request: Request) -> AnalysisRunView:
    result = require_result(analysis_run_id, request)
    return AnalysisRunView(
        analysis_run_id=analysis_run_id,
        run=result.run,
        provider=result.provider,
        statistics=result.statistics,
        semantic_analysis=(semantic_summary(result.semantic_analysis) if result.semantic_analysis else None),
        evidence_validation=(evidence_summary(result.evidence_validation) if result.evidence_validation else None),
    )


def _run_semantic_analysis(
    service: SemanticAnalysisService,
    analysis_run_id: str,
    output_language: AnalysisOutputLanguage,
    ui_language: Optional[str],
) -> None:
    try:
        service.analyze(
            analysis_run_id,
            output_language=output_language,
            ui_language=ui_language,
        )
    except SemanticAnalysisError:
        # The service persists terminal failure details for polling clients.
        return


@router.post("/{analysis_run_id}/semantic", response_model=AnalysisRunView, status_code=202)
def start_semantic_analysis(
    analysis_run_id: str,
    payload: SemanticAnalysisRequest,
    request: Request,
) -> AnalysisRunView:
    try:
        selected_output_language = payload.output_language
        if selected_output_language is None:
            selected_output_language = require_result(analysis_run_id, request).run.output_language
        queued = get_semantic_service(request).queue(
            analysis_run_id,
            output_language=selected_output_language,
            ui_language=payload.ui_language,
        )
    except SemanticAnalysisError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    Thread(
        target=_run_semantic_analysis,
        args=(
            get_semantic_service(request),
            analysis_run_id,
            queued.run.output_language,
            payload.ui_language,
        ),
        daemon=True,
        name=f"semantic-{analysis_run_id}",
    ).start()
    return AnalysisRunView(
        analysis_run_id=analysis_run_id,
        run=queued.run,
        provider=queued.provider,
        statistics=queued.statistics,
        semantic_analysis=(semantic_summary(queued.semantic_analysis) if queued.semantic_analysis else None),
        evidence_validation=(evidence_summary(queued.evidence_validation) if queued.evidence_validation else None),
    )


def _run_evidence_validation(
    service: EvidenceValidationService,
    analysis_run_id: str,
    candidate_ids: Optional[List[str]],
) -> None:
    try:
        service.validate(analysis_run_id, candidate_ids=candidate_ids)
    except EvidenceValidationError:
        # The service persists terminal failure details for polling clients.
        return


@router.post("/{analysis_run_id}/evidence", response_model=AnalysisRunView, status_code=202)
def start_evidence_validation(
    analysis_run_id: str,
    payload: EvidenceValidationRequest,
    request: Request,
) -> AnalysisRunView:
    try:
        queued = get_evidence_service(request).queue(
            analysis_run_id,
            candidate_ids=payload.candidate_ids,
        )
    except EvidenceValidationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    Thread(
        target=_run_evidence_validation,
        args=(get_evidence_service(request), analysis_run_id, payload.candidate_ids),
        daemon=True,
        name=f"evidence-{analysis_run_id}",
    ).start()
    return AnalysisRunView(
        analysis_run_id=analysis_run_id,
        run=queued.run,
        provider=queued.provider,
        statistics=queued.statistics,
        semantic_analysis=(semantic_summary(queued.semantic_analysis) if queued.semantic_analysis else None),
        evidence_validation=(evidence_summary(queued.evidence_validation) if queued.evidence_validation else None),
    )


@router.get("/{analysis_run_id}/reviews", response_model=ReviewsView)
def get_cleaned_reviews(analysis_run_id: str, request: Request) -> ReviewsView:
    result = require_result(analysis_run_id, request)
    return ReviewsView(analysis_run_id=analysis_run_id, reviews=result.reviews)


@router.get("/{analysis_run_id}/topics", response_model=TopicsView)
def get_topics(analysis_run_id: str, request: Request) -> TopicsView:
    result = require_result(analysis_run_id, request)
    consolidated = result.semantic_analysis.consolidated_result if result.semantic_analysis else None
    return TopicsView(
        analysis_run_id=analysis_run_id,
        topics=consolidated.topic_candidates if consolidated else [],
    )


@router.get("/{analysis_run_id}/finding-candidates", response_model=FindingCandidatesView)
def get_finding_candidates(analysis_run_id: str, request: Request) -> FindingCandidatesView:
    result = require_result(analysis_run_id, request)
    consolidated = result.semantic_analysis.consolidated_result if result.semantic_analysis else None
    return FindingCandidatesView(
        analysis_run_id=analysis_run_id,
        finding_candidates=consolidated.finding_candidates if consolidated else [],
    )


@router.get("/{analysis_run_id}/findings", response_model=FindingsView)
def get_findings(analysis_run_id: str, request: Request) -> FindingsView:
    result = require_result(analysis_run_id, request)
    evidence = result.evidence_validation
    return FindingsView(
        analysis_run_id=analysis_run_id,
        findings=evidence.findings if evidence else [],
        audits=evidence.audits if evidence else [],
    )
