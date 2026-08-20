from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.llm import LLMProvider, create_llm_provider
from app.services import (
    EvidenceValidationService,
    IngestionService,
    ProductPlanningService,
    SemanticAnalysisService,
)
from app.storage import RunStore


def create_app(
    settings: Optional[Settings] = None,
    semantic_provider_factory: Callable[[Settings], LLMProvider] = create_llm_provider,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    application = FastAPI(
        title="App Review Insights API",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    run_store = RunStore(settings.sqlite_database_path)
    run_store.initialize()
    application.state.run_store = run_store
    application.state.ingestion_service = IngestionService(settings, run_store)
    application.state.semantic_analysis_service = SemanticAnalysisService(
        settings,
        run_store,
        provider_factory=semantic_provider_factory,
    )
    application.state.evidence_validation_service = EvidenceValidationService(
        settings,
        run_store,
        provider_factory=semantic_provider_factory,
    )
    application.state.product_planning_service = ProductPlanningService(
        settings,
        run_store,
        provider_factory=semantic_provider_factory,
    )
    application.include_router(health_router, prefix=settings.api_prefix)
    application.include_router(analysis_router, prefix=settings.api_prefix)
    return application


app = create_app()
