from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.models import AnalysisRunView, IngestionResult, ReviewsView
from app.providers.errors import IngestionError
from app.services import IngestionService
from app.storage import RunStore


router = APIRouter(prefix="/analysis", tags=["analysis"])


class AppStoreAnalysisRequest(BaseModel):
    app_store_url: str = Field(min_length=1)
    analysis_goal: Optional[str] = None


def get_service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


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
        )
    except IngestionError as error:
        raise_http_error(error)


@router.post("/import/csv", response_model=IngestionResult)
async def create_csv_run(
    request: Request,
    file: UploadFile = File(...),
    analysis_goal: Optional[str] = Form(default=None),
) -> IngestionResult:
    try:
        data = await file.read(get_service(request).settings.max_upload_bytes + 1)
        return get_service(request).ingest_csv(data, analysis_goal)
    except IngestionError as error:
        raise_http_error(error)


@router.post("/import/json", response_model=IngestionResult)
async def create_json_run(
    request: Request,
    file: UploadFile = File(...),
    analysis_goal: Optional[str] = Form(default=None),
) -> IngestionResult:
    try:
        data = await file.read(get_service(request).settings.max_upload_bytes + 1)
        return get_service(request).ingest_json(data, analysis_goal)
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
    )


@router.get("/{analysis_run_id}/reviews", response_model=ReviewsView)
def get_cleaned_reviews(analysis_run_id: str, request: Request) -> ReviewsView:
    result = require_result(analysis_run_id, request)
    return ReviewsView(analysis_run_id=analysis_run_id, reviews=result.reviews)
