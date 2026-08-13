import json
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.llm import create_llm_provider  # noqa: E402
from app.cleaning import clean_reviews  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisOutputLanguage,
    AnalysisRun,
    AnalysisRunStatus,
    IngestionResult,
    PipelineStage,
    ProviderMetadata,
    SourceType,
)
from app.providers import JSONProvider  # noqa: E402
from app.services.semantic import SemanticAnalysisService  # noqa: E402
from app.storage import RunStore  # noqa: E402


def main() -> int:
    settings = Settings(_env_file=PROJECT_ROOT / ".env", llm_review_batch_size=12)
    if not settings.llm_api_key or not settings.llm_api_key.get_secret_value():
        print("REAL_LLM_SMOKE_SKIPPED: LLM_API_KEY is not configured.")
        return 2

    data = (PROJECT_ROOT / "sample_data" / "semantic_smoke_reviews.json").read_bytes()
    batch = JSONProvider(
        data,
        max_upload_bytes=settings.max_upload_bytes,
        max_review_rows=settings.max_review_rows,
    ).load()
    run_id = "RUN-REAL-SMOKE"
    reviews, statistics, rejected = clean_reviews(batch, analysis_run_id=run_id)
    with tempfile.TemporaryDirectory(prefix="app-review-insights-smoke-") as temporary_directory:
        smoke_store = RunStore(Path(temporary_directory) / "semantic-smoke.db")
        smoke_store.initialize()
        smoke_store.save(
            IngestionResult(
                analysis_run_id=run_id,
                run=AnalysisRun(
                    id=run_id,
                    source_type=SourceType.JSON,
                    analysis_goal="Identify reliability problems that disrupt podcast listening.",
                    output_language=AnalysisOutputLanguage.EN_US,
                    resolved_output_language=AnalysisOutputLanguage.EN_US,
                    status=AnalysisRunStatus.COMPLETED,
                    current_stage=PipelineStage.CLEANING_AND_NORMALIZATION,
                    last_successful_stage=PipelineStage.CLEANING_AND_NORMALIZATION,
                    progress=100,
                    total_review_count=len(reviews),
                ),
                provider=ProviderMetadata(
                    analysis_run_id=run_id,
                    source=batch.source,
                    collection_time=batch.collection_time,
                    source_limitations=batch.source_limitations,
                ),
                statistics=statistics,
                reviews=reviews,
                rejected_rows=rejected,
            )
        )
        service = SemanticAnalysisService(settings, smoke_store, provider_factory=create_llm_provider)
        result = service.analyze(
            run_id,
            output_language=AnalysisOutputLanguage.EN_US,
            ui_language="zh-CN",
        )
        semantic = result.semantic_analysis
        if semantic is None or semantic.consolidated_result is None:
            raise RuntimeError("The real model did not produce consolidated semantic results.")
        allowed_ids = {review.id for review in reviews}
        cited_ids = {
            review_id
            for finding in semantic.consolidated_result.finding_candidates
            for review_id in finding.supporting_review_ids
        }
        if not cited_ids or not cited_ids.issubset(allowed_ids):
            raise RuntimeError("The real model returned missing or hallucinated Review IDs.")
        summary = {
            "provider": semantic.model_provider,
            "model": semantic.model_name,
            "review_count": semantic.analyzed_review_count,
            "batch_count": semantic.batch_count,
            "output_language": semantic.resolved_output_language.value,
            "topic_names": [topic.name for topic in semantic.consolidated_result.topic_candidates],
            "finding_candidate_count": len(semantic.consolidated_result.finding_candidates),
            "cited_review_ids_valid": True,
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
