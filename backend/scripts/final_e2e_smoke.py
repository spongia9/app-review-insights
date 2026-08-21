"""Run the final real-provider E2E hard gates without printing credentials."""

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.models import AnalysisOutputLanguage  # noqa: E402
from app.services import (  # noqa: E402
    EvidenceValidationService,
    FullPipelineService,
    IngestionService,
    ProductPlanningService,
    SemanticAnalysisService,
)
from app.storage import RunStore  # noqa: E402


WORKOUT_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


def services(settings: Settings):
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    semantic = SemanticAnalysisService(settings, store)
    evidence = EvidenceValidationService(settings, store)
    product = ProductPlanningService(settings, store)
    return store, IngestionService(settings, store), FullPipelineService(
        store,
        semantic,
        evidence,
        product,
    )


def complete(pipeline, result, language: AnalysisOutputLanguage, ui_language: str):
    pipeline.queue(
        result.analysis_run_id,
        output_language=language,
        ui_language=ui_language,
    )
    final = pipeline.execute(
        result.analysis_run_id,
        output_language=language,
        ui_language=ui_language,
    )
    if final.final_traceability is None:
        raise RuntimeError(f"{result.analysis_run_id}: final traceability is missing")
    if final.final_traceability.coverage.hard_failures:
        raise RuntimeError(
            f"{result.analysis_run_id}: {final.final_traceability.coverage.hard_failures}"
        )
    if final.final_traceability.coverage.overall_traceability_coverage != 1:
        raise RuntimeError(f"{result.analysis_run_id}: overall coverage is not 100%")
    return final


def summary(label: str, result) -> dict:
    semantic = result.semantic_analysis
    evidence = result.evidence_validation
    planning = result.product_planning
    traceability = result.final_traceability
    topics = semantic.consolidated_result.topic_candidates
    return {
        "scenario": label,
        "run_id": result.analysis_run_id,
        "source": result.provider.source,
        "storefront": result.provider.storefront,
        "live_collection": result.provider.is_live_collection,
        "reviews": len(result.reviews),
        "analyzed_reviews": semantic.analyzed_review_count,
        "topics": [topic.name for topic in topics],
        "findings": len(evidence.findings),
        "requirements": len(planning.requirements),
        "versions": len(planning.version_plan.items),
        "test_cases": len(planning.test_cases),
        "provider": semantic.model_provider,
        "model": semantic.model_name,
        "output_language": semantic.resolved_output_language.value,
        "overall_traceability": traceability.coverage.overall_traceability_coverage,
        "hard_failures": len(traceability.coverage.hard_failures),
        "status": result.run.status.value,
        "cached_demo": result.cached_demo is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-workout",
        action="store_true",
        help="Reuse a separately recorded Workout acceptance and run imported-data gates only.",
    )
    args = parser.parse_args()
    settings = Settings(
        _env_file=PROJECT_ROOT / ".env",
        sqlite_database_path=BACKEND_ROOT / "data" / "phase7-acceptance.db",
    )
    if not settings.llm_api_key or not settings.llm_api_key.get_secret_value().strip():
        print("SKIP: LLM_API_KEY is not configured.")
        return 2
    store, ingestion, pipeline = services(settings)
    results = []

    if not args.skip_workout:
        workout = ingestion.ingest_app_store(
            WORKOUT_URL,
            "重点分析订阅价格、免费功能减少、广告退出体验和训练内容使用体验。",
            AnalysisOutputLanguage.ZH_CN,
        )
        if not workout.provider.is_live_collection or workout.provider.storefront != "us":
            raise RuntimeError("Workout source is not a verified live U.S. collection")
        workout_text = [review.text for review in workout.reviews]
        workout_final = complete(pipeline, workout, AnalysisOutputLanguage.ZH_CN, "zh-CN")
        if workout_text != [review.text for review in workout_final.reviews]:
            raise RuntimeError("Workout source Review text changed")
        results.append(summary("real_workout_app", workout_final))

    music_data = (PROJECT_ROOT / "sample_data" / "music_unknown_domain.csv").read_bytes()
    music = ingestion.ingest_csv(
        music_data,
        "Focus on offline playback, lyrics, collaborative playlists, and recommendations.",
        AnalysisOutputLanguage.EN_US,
    )
    music_text = [review.text for review in music.reviews]
    music_final = complete(pipeline, music, AnalysisOutputLanguage.EN_US, "en-US")
    if music_text != [review.text for review in music_final.reviews]:
        raise RuntimeError("Music source Review text changed")
    music_topics = " ".join(
        topic.name.lower()
        for topic in music_final.semantic_analysis.consolidated_result.topic_candidates
    )
    expected = ("offline", "lyric", "playlist", "recommend")
    if not all(term in music_topics for term in expected):
        raise RuntimeError(f"Unknown-domain topics missed expected concepts: {music_topics}")
    if any(term in music_topics for term in ("workout", "exercise", "fitness")):
        raise RuntimeError("Workout-specific taxonomy leaked into the Music result")
    results.append(summary("unknown_music_csv", music_final))

    mixed_data = (PROJECT_ROOT / "sample_data" / "mixed_language_reviews.json").read_bytes()
    mixed = ingestion.ingest_json(
        mixed_data,
        "识别播客播放、队列、文字稿、通知和设备控制中的主要问题。",
        AnalysisOutputLanguage.ZH_CN,
    )
    mixed_text = [review.text for review in mixed.reviews]
    mixed_final = complete(pipeline, mixed, AnalysisOutputLanguage.ZH_CN, "zh-CN")
    if mixed_text != [review.text for review in mixed_final.reviews]:
        raise RuntimeError("Mixed-language source Review text changed")
    topic_names = [
        topic.name
        for topic in mixed_final.semantic_analysis.consolidated_result.topic_candidates
    ]
    if not any(any("\u4e00" <= character <= "\u9fff" for character in name) for name in topic_names):
        raise RuntimeError("zh-CN output did not produce Chinese Topics")
    results.append(summary("json_mixed_language", mixed_final))

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
