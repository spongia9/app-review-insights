from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.service_name)
