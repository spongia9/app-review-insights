from threading import Thread
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.models import (
    AnalysisOutputLanguage,
    AnalysisRunView,
    FindingsView,
    FindingCandidatesView,
    IngestionResult,
    ProductPlanningView,
    ReviewsView,
    TraceabilityView,
    TopicsView,
)
from app.providers.errors import IngestionError
from app.services import (
    CachedDemoError,
    EvidenceValidationError,
    EvidenceValidationService,
    FullPipelineError,
    FullPipelineService,
    IngestionService,
    ProductPlanningError,
    ProductPlanningService,
    SemanticAnalysisError,
    SemanticAnalysisService,
    load_workout_demo,
)
from app.services.evidence import evidence_summary
from app.services.product_planning import product_planning_summary
from app.services.semantic import semantic_summary
from app.services.traceability import final_traceability_summary
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


class ProductPlanningRequest(BaseModel):
    pass


def get_service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


def get_semantic_service(request: Request) -> SemanticAnalysisService:
    return request.app.state.semantic_analysis_service


def get_evidence_service(request: Request) -> EvidenceValidationService:
    return request.app.state.evidence_validation_service


def get_product_planning_service(request: Request) -> ProductPlanningService:
    return request.app.state.product_planning_service


def get_full_pipeline_service(request: Request) -> FullPipelineService:
    return request.app.state.full_pipeline_service


def analysis_view(result: IngestionResult) -> AnalysisRunView:
    return AnalysisRunView(
        analysis_run_id=result.analysis_run_id,
        run=result.run,
        provider=result.provider,
        statistics=result.statistics,
        semantic_analysis=(semantic_summary(result.semantic_analysis) if result.semantic_analysis else None),
        evidence_validation=(evidence_summary(result.evidence_validation) if result.evidence_validation else None),
        product_planning=(product_planning_summary(result.product_planning) if result.product_planning else None),
        final_traceability=(
            final_traceability_summary(result.final_traceability)
            if result.final_traceability
            else None
        ),
        audit_event_count=len(result.audit_events),
    )


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


@router.post("/demo/workout", response_model=IngestionResult)
def load_cached_workout_demo(request: Request) -> IngestionResult:
    try:
        return load_workout_demo(get_store(request))
    except CachedDemoError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": error.message},
        ) from error


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
    return analysis_view(require_result(analysis_run_id, request))


@router.get("/{analysis_run_id}/workspace", response_model=IngestionResult)
def get_analysis_workspace(analysis_run_id: str, request: Request) -> IngestionResult:
    """Return the persisted run and its intermediate artifacts for workspace restore."""
    return require_result(analysis_run_id, request)


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
    return analysis_view(queued)


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
    return analysis_view(queued)


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


def _run_product_planning(
    service: ProductPlanningService,
    analysis_run_id: str,
) -> None:
    try:
        service.generate(analysis_run_id)
    except ProductPlanningError:
        # The service persists terminal failure details for polling clients.
        return


@router.post("/{analysis_run_id}/product-plan", response_model=AnalysisRunView, status_code=202)
def start_product_planning(
    analysis_run_id: str,
    _: ProductPlanningRequest,
    request: Request,
) -> AnalysisRunView:
    try:
        queued = get_product_planning_service(request).queue(analysis_run_id)
    except ProductPlanningError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    Thread(
        target=_run_product_planning,
        args=(get_product_planning_service(request), analysis_run_id),
        daemon=True,
        name=f"product-plan-{analysis_run_id}",
    ).start()
    return analysis_view(queued)


def _run_full_pipeline(
    service: FullPipelineService,
    analysis_run_id: str,
    output_language: AnalysisOutputLanguage,
    ui_language: Optional[str],
) -> None:
    try:
        service.execute(
            analysis_run_id,
            output_language=output_language,
            ui_language=ui_language,
        )
    except FullPipelineError:
        # The orchestrator and stage services persist the truthful failure boundary.
        return


@router.post("/{analysis_run_id}/pipeline", response_model=AnalysisRunView, status_code=202)
def start_full_pipeline(
    analysis_run_id: str,
    payload: SemanticAnalysisRequest,
    request: Request,
) -> AnalysisRunView:
    try:
        current = require_result(analysis_run_id, request)
        selected = payload.output_language or current.run.output_language
        queued = get_full_pipeline_service(request).queue(
            analysis_run_id,
            output_language=selected,
            ui_language=payload.ui_language,
        )
    except FullPipelineError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    Thread(
        target=_run_full_pipeline,
        args=(
            get_full_pipeline_service(request),
            analysis_run_id,
            queued.run.output_language,
            payload.ui_language,
        ),
        daemon=True,
        name=f"full-pipeline-{analysis_run_id}",
    ).start()
    return analysis_view(queued)


@router.get("/{analysis_run_id}/traceability", response_model=TraceabilityView)
def get_traceability(analysis_run_id: str, request: Request) -> TraceabilityView:
    result = require_result(analysis_run_id, request)
    return TraceabilityView(
        analysis_run_id=analysis_run_id,
        traceability=result.final_traceability,
        audit_events=result.audit_events,
    )


@router.post("/{analysis_run_id}/traceability/validate", response_model=TraceabilityView)
def validate_traceability(analysis_run_id: str, request: Request) -> TraceabilityView:
    result = get_full_pipeline_service(request).validate_existing(analysis_run_id)
    return TraceabilityView(
        analysis_run_id=analysis_run_id,
        traceability=result.final_traceability,
        audit_events=result.audit_events,
    )


@router.get("/{analysis_run_id}/product-plan", response_model=ProductPlanningView)
def get_product_plan(analysis_run_id: str, request: Request) -> ProductPlanningView:
    result = require_result(analysis_run_id, request)
    return ProductPlanningView(
        analysis_run_id=analysis_run_id,
        product_planning=result.product_planning,
    )


@router.get("/{analysis_run_id}/product-plan/prd.md", response_class=Response)
def download_product_prd(analysis_run_id: str, request: Request) -> Response:
    result = require_result(analysis_run_id, request)
    artifact = result.product_planning.prd_artifact if result.product_planning else None
    if artifact is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRD_NOT_AVAILABLE",
                "message": "The validated PRD artifact is not available for this analysis run.",
            },
        )
    return Response(
        content=artifact.rendered_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="PRD.md"'},
    )
