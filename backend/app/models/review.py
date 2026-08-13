from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import Field

from app.models.base import RunScopedModel


class Review(RunScopedModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_review_id: Optional[str] = None
    app_id: Optional[str] = None
    author: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=1, le=5)
    title: Optional[str] = None
    text: str = Field(min_length=1)
    version: Optional[str] = None
    language: Optional[str] = None
    created_at: Optional[datetime] = None
    storefront: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
