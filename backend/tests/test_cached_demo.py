from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm import LLMProviderError, create_llm_provider
from app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def no_key_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "no-key.db",
        llm_provider="deepseek",
        llm_model="deepseek-v4-flash",
        llm_api_key=None,
    )


def test_missing_api_key_fails_locally_with_actionable_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(LLMProviderError) as captured:
        create_llm_provider(no_key_settings(tmp_path))

    assert captured.value.code == "LLM_NOT_CONFIGURED"
    assert captured.value.retryable is False
    assert "LLM_API_KEY" in captured.value.message
    assert "cached demo" in captured.value.message


def test_packaged_cached_demo_loads_without_api_key_and_preserves_provenance(tmp_path: Path) -> None:
    app = create_app(settings=no_key_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/analysis/demo/workout")
        assert response.status_code == 200
        payload = response.json()

        assert payload["cached_demo"]["CACHED_DEMO"] is True
        assert payload["cached_demo"]["source"] == "apple_customer_reviews_rss"
        assert payload["cached_demo"]["model_provider"] == "deepseek"
        assert payload["cached_demo"]["model_name"]
        assert payload["provider"]["is_live_collection"] is False
        assert payload["provider"]["source"].startswith("cached_demo:")
        assert payload["semantic_analysis"]["consolidated_result"]["topic_candidates"]
        assert payload["evidence_validation"]["findings"]
        assert payload["product_planning"]["requirements"]
        assert payload["product_planning"]["version_plan"]["items"]
        assert payload["product_planning"]["prd_artifact"]["rendered_markdown"]
        assert payload["product_planning"]["test_cases"]
        assert payload["final_traceability"]["matrix"]
        assert not payload["final_traceability"]["coverage"]["hard_failures"]

        run_id = payload["analysis_run_id"]
        restored = client.get(f"/api/analysis/{run_id}/workspace")
        traceability = client.get(f"/api/analysis/{run_id}/traceability")
        assert restored.status_code == 200
        assert restored.json()["cached_demo"]["CACHED_DEMO"] is True
        assert traceability.status_code == 200
        assert traceability.json()["traceability"]["coverage"]["overall_traceability_coverage"] == 1


@pytest.mark.parametrize(
    ("filename", "source", "minimum_clean"),
    [
        ("workout_compatible_sample.json", "json", 8),
        ("music_unknown_domain.csv", "csv", 24),
        ("mixed_language_reviews.json", "json", 24),
        ("semantic_smoke_reviews.json", "json", 12),
        ("sample_reviews.csv", "csv", 3),
        ("conflicting_evidence_reviews.json", "json", 10),
        ("insufficient_evidence_reviews.json", "json", 1),
    ],
)
def test_submission_sample_dataset_imports(
    tmp_path: Path,
    filename: str,
    source: str,
    minimum_clean: int,
) -> None:
    app = create_app(settings=no_key_settings(tmp_path))
    sample = PROJECT_ROOT / "sample_data" / filename
    with TestClient(app) as client, sample.open("rb") as handle:
        response = client.post(
            f"/api/analysis/import/{source}",
            files={"file": (filename, handle, "application/json" if source == "json" else "text/csv")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["statistics"]["clean_review_count"] >= minimum_clean
    assert len(payload["reviews"]) == payload["statistics"]["clean_review_count"]
