from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.cleaning import clean_reviews
from app.core.config import Settings
from app.models import (
    AnalysisOutputLanguage,
    AnalysisRun,
    AnalysisRunStatus,
    IngestionResult,
    PipelineStage,
    ProviderMetadata,
    SourceType,
)
from app.providers import AppStoreProvider, CSVProvider, JSONProvider, ReviewProvider
from app.providers.errors import IngestionError
from app.storage import RunStore


class IngestionService:
    def __init__(self, settings: Settings, store: RunStore) -> None:
        self.settings = settings
        self.store = store

    def ingest_app_store(
        self,
        app_store_url: str,
        analysis_goal: Optional[str],
        output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.FOLLOW_UI,
    ) -> IngestionResult:
        provider = AppStoreProvider(
            app_store_url,
            max_pages=self.settings.app_store_max_pages,
            max_review_rows=self.settings.max_review_rows,
            timeout_seconds=self.settings.app_store_request_timeout_seconds,
        )
        return self._run(provider, SourceType.APP_STORE, analysis_goal, output_language)

    def ingest_csv(
        self,
        data: bytes,
        analysis_goal: Optional[str],
        output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.FOLLOW_UI,
    ) -> IngestionResult:
        provider = CSVProvider(
            data,
            max_upload_bytes=self.settings.max_upload_bytes,
            max_review_rows=self.settings.max_review_rows,
        )
        return self._run(provider, SourceType.CSV, analysis_goal, output_language)

    def ingest_json(
        self,
        data: bytes,
        analysis_goal: Optional[str],
        output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.FOLLOW_UI,
    ) -> IngestionResult:
        provider = JSONProvider(
            data,
            max_upload_bytes=self.settings.max_upload_bytes,
            max_review_rows=self.settings.max_review_rows,
        )
        return self._run(provider, SourceType.JSON, analysis_goal, output_language)

    def _run(
        self,
        provider: ReviewProvider,
        source_type: SourceType,
        analysis_goal: Optional[str],
        output_language: AnalysisOutputLanguage,
    ) -> IngestionResult:
        run_id = f"RUN-{uuid4().hex[:12].upper()}"
        started_at = datetime.now(timezone.utc)
        run = AnalysisRun(
            id=run_id,
            source_type=source_type,
            analysis_goal=analysis_goal,
            output_language=output_language,
            resolved_output_language=(
                output_language
                if output_language != AnalysisOutputLanguage.FOLLOW_UI
                else AnalysisOutputLanguage.ZH_CN
            ),
            status=AnalysisRunStatus.PENDING,
            current_stage=PipelineStage.DATA_ACQUISITION,
            progress=0,
        )
        initial_provider = ProviderMetadata(
            analysis_run_id=run_id,
            source=getattr(provider, "source", source_type.value),
            storefront=getattr(provider, "storefront", None),
            collection_time=started_at,
            source_limitations=[],
            is_live_collection=False,
            storefront_verified=False,
        )
        self.store.save(
            IngestionResult(
                analysis_run_id=run_id,
                run=run,
                provider=initial_provider,
            )
        )
        run = run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "progress": 10,
                "started_at": started_at,
            }
        )

        try:
            batch = provider.load()
            run = run.model_copy(
                update={
                    "app_id": batch.app_id,
                    "last_successful_stage": PipelineStage.DATA_ACQUISITION,
                    "current_stage": PipelineStage.CLEANING_AND_NORMALIZATION,
                    "progress": 60,
                }
            )
            provider_metadata = ProviderMetadata(
                analysis_run_id=run_id,
                source=batch.source,
                storefront=batch.storefront,
                collection_time=batch.collection_time,
                source_limitations=batch.source_limitations,
                is_live_collection=batch.is_live_collection,
                storefront_verified=batch.storefront_verified,
            )
            self.store.save(
                IngestionResult(
                    analysis_run_id=run_id,
                    run=run,
                    provider=provider_metadata,
                )
            )
            reviews, statistics, rejected_rows = clean_reviews(
                batch,
                analysis_run_id=run_id,
            )
            warnings = list(batch.source_limitations)
            if rejected_rows:
                warnings.append(f"{len(rejected_rows)} input rows were rejected during ingestion.")
            status = AnalysisRunStatus.WARNING if warnings else AnalysisRunStatus.COMPLETED
            run = run.model_copy(
                update={
                    "status": status,
                    "last_successful_stage": PipelineStage.CLEANING_AND_NORMALIZATION,
                    "current_stage": PipelineStage.CLEANING_AND_NORMALIZATION,
                    "progress": 100,
                    "warnings": warnings,
                    "total_review_count": statistics.raw_review_count,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            result = IngestionResult(
                analysis_run_id=run_id,
                run=run,
                provider=provider_metadata,
                statistics=statistics,
                reviews=reviews,
                rejected_rows=rejected_rows,
            )
            self.store.save(result)
            return result
        except IngestionError as error:
            failed_run = run.model_copy(
                update={
                    "status": AnalysisRunStatus.FAILED,
                    "progress": 0,
                    "errors": [error.message],
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            self.store.save(
                IngestionResult(
                    analysis_run_id=run_id,
                    run=failed_run,
                    provider=ProviderMetadata(
                        analysis_run_id=run_id,
                        source=getattr(provider, "source", source_type.value),
                        storefront=getattr(provider, "storefront", None),
                        collection_time=datetime.now(timezone.utc),
                        source_limitations=[error.message],
                        is_live_collection=False,
                        storefront_verified=False,
                    ),
                )
            )
            raise error.with_run_id(run_id) from error
