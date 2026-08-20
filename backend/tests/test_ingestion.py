import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cleaning import clean_reviews
from app.main import create_app
from app.providers import AppStoreProvider, CSVProvider, JSONProvider, parse_us_app_store_url
from app.providers.base import ProviderBatch, ReviewCandidate
from app.providers.errors import IngestionError


RUN_ID = "RUN-INGESTION-001"


def sample_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "sample_data" / name


def test_app_store_url_parsing_and_us_storefront_rule() -> None:
    parsed = parse_us_app_store_url(
        "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
    )
    assert parsed.app_id == "839285684"
    assert parsed.storefront == "us"


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "http://apps.apple.com/us/app/example/id123",
        "https://apps.apple.com/cn/app/example/id123",
        "https://example.com/us/app/example/id123",
        "https://apps.apple.com/us/app/example/not-an-id",
    ],
)
def test_app_store_url_rejects_invalid_or_non_us_urls(url: str) -> None:
    with pytest.raises(IngestionError) as exc_info:
        parse_us_app_store_url(url)
    assert exc_info.value.code == "INVALID_APP_STORE_URL"


def test_csv_valid_import_cleaning_and_statistics() -> None:
    provider = CSVProvider(
        sample_path("sample_reviews.csv").read_bytes(),
        max_upload_bytes=10 * 1024 * 1024,
        max_review_rows=10_000,
    )
    result = provider.provide(RUN_ID)

    assert all(review.analysis_run_id == RUN_ID for review in result.reviews)
    assert [review.id for review in result.reviews] == ["R000001", "R000002", "R000003"]
    assert result.statistics.raw_review_count == 6
    assert result.statistics.clean_review_count == 3
    assert result.statistics.duplicate_count == 1
    assert result.statistics.empty_count == 1
    assert result.statistics.invalid_count == 1
    assert result.statistics.retention_rate == 0.5


def test_csv_supports_utf8_bom_and_aliases() -> None:
    data = "review_id,review,stars\nsource-1,  Useful   review  ,4\n".encode("utf-8-sig")
    review = CSVProvider(data, max_upload_bytes=1000, max_review_rows=10).provide(RUN_ID).reviews[0]
    assert review.source_review_id == "source-1"
    assert review.text == "Useful review"
    assert review.rating == 4


def test_csv_malformed_input_is_structured_error() -> None:
    with pytest.raises(IngestionError) as exc_info:
        CSVProvider(b"title,rating\nMissing text,5", max_upload_bytes=1000, max_review_rows=10).load()
    assert exc_info.value.code == "INVALID_IMPORT_SCHEMA"


def test_json_valid_array_and_wrapper_import() -> None:
    array_data = json.dumps([{"id": "one", "body": "Good", "score": 5}]).encode()
    array_result = JSONProvider(array_data, max_upload_bytes=1000, max_review_rows=10).provide(RUN_ID)
    wrapper_result = JSONProvider(
        sample_path("sample_reviews.json").read_bytes(),
        max_upload_bytes=10_000,
        max_review_rows=10,
    ).provide(RUN_ID)
    assert array_result.reviews[0].source_review_id == "one"
    assert len(wrapper_result.reviews) == 2


def test_json_malformed_and_unsupported_shape_are_structured_errors() -> None:
    for data in (b"{broken", b'{"items": []}'):
        with pytest.raises(IngestionError) as exc_info:
            JSONProvider(data, max_upload_bytes=1000, max_review_rows=10).load()
        assert exc_info.value.code == "INVALID_JSON"


def test_file_and_row_limits_are_enforced() -> None:
    with pytest.raises(IngestionError) as size_error:
        CSVProvider(b"text\nreview", max_upload_bytes=4, max_review_rows=10).load()
    assert size_error.value.code == "FILE_TOO_LARGE"

    rows = json.dumps([{"text": "one"}, {"text": "two"}]).encode()
    with pytest.raises(IngestionError) as rows_error:
        JSONProvider(rows, max_upload_bytes=1000, max_review_rows=1).load()
    assert rows_error.value.code == "TOO_MANY_REVIEWS"


def test_duplicate_by_source_id_and_fingerprint_and_run_isolation() -> None:
    candidates = [
        ReviewCandidate(source="fixture", raw_data={}, source_review_id="s1", text="Alpha", rating=5),
        ReviewCandidate(source="fixture", raw_data={}, source_review_id="s1", text="Changed", rating=1),
        ReviewCandidate(source="fixture", raw_data={}, title="Same", text="Beta", rating=4),
        ReviewCandidate(source="fixture", raw_data={}, title=" Same ", text=" Beta ", rating="4"),
    ]
    batch = ProviderBatch(
        source="fixture",
        collection_time=datetime.now(timezone.utc),
        candidates=candidates,
        raw_review_count=4,
    )
    first_reviews, first_stats, _ = clean_reviews(batch, analysis_run_id="RUN-A")
    second_reviews, _, _ = clean_reviews(batch, analysis_run_id="RUN-B")

    assert first_stats.duplicate_count == 2
    assert [review.id for review in first_reviews] == ["R000001", "R000002"]
    assert first_reviews[0].analysis_run_id == "RUN-A"
    assert second_reviews[0].analysis_run_id == "RUN-B"


def test_provider_failure_does_not_fabricate_reviews() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    provider = AppStoreProvider(
        "https://apps.apple.com/us/app/example/id123456",
        max_pages=1,
        max_review_rows=50,
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(IngestionError) as exc_info:
        provider.provide(RUN_ID)
    assert exc_info.value.code == "APP_STORE_COLLECTION_FAILED"


def test_app_store_provider_maps_mock_feed_and_preserves_us_provenance() -> None:
    payload = {
        "feed": {
            "entry": [
                {
                    "id": {"label": "apple-review-1"},
                    "author": {"name": {"label": "Reviewer"}},
                    "im:rating": {"label": "5"},
                    "title": {"label": "Great"},
                    "content": {"label": "Works well"},
                    "im:version": {"label": "1.2.3"},
                    "updated": {"label": "2026-08-01T10:00:00Z"},
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "itunes.apple.com"
        assert request.url.path == "/us/rss/customerreviews/id=123456/sortby=mostrecent/page=1/json"
        return httpx.Response(200, json=payload, request=request)

    provider = AppStoreProvider(
        "https://apps.apple.com/us/app/example/id123456",
        max_pages=1,
        max_review_rows=50,
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.provide(RUN_ID)
    assert result.batch.storefront == "us"
    assert result.batch.storefront_verified is True
    assert result.reviews[0].storefront == "us"
    assert result.reviews[0].source_review_id == "apple-review-1"


def test_app_store_provider_does_not_inherit_environment_proxy_by_default() -> None:
    provider = AppStoreProvider(
        "https://apps.apple.com/us/app/example/id123456",
        max_pages=1,
        max_review_rows=50,
        timeout_seconds=1,
    )
    assert provider.trust_environment_proxy is False


def test_analysis_api_csv_run_and_retrieval(tmp_path: Path) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    original_path = settings.sqlite_database_path
    settings.sqlite_database_path = tmp_path / "api-test.db"
    application = create_app()
    try:
        with TestClient(application) as client:
            response = client.post(
                "/api/analysis/import/csv",
                files={"file": ("sample.csv", b"text,rating\nSolid,4", "text/csv")},
                data={"analysis_goal": "Focus on low ratings"},
            )
            assert response.status_code == 200
            payload = response.json()
            run_id = payload["analysis_run_id"]
            assert payload["run"]["analysis_goal"] == "Focus on low ratings"
            assert payload["run"]["current_stage"] == "CLEANING_AND_NORMALIZATION"
            assert payload["statistics"]["clean_review_count"] == 1

            stored = client.get(f"/api/analysis/{run_id}")
            assert stored.status_code == 200
            assert stored.json()["run"]["id"] == run_id

            reviews = client.get(f"/api/analysis/{run_id}/reviews")
            assert reviews.status_code == 200
            assert reviews.json()["reviews"][0]["analysis_run_id"] == run_id
    finally:
        settings.sqlite_database_path = original_path
        get_settings.cache_clear()


def test_analysis_api_returns_structured_import_error(tmp_path: Path) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.sqlite_database_path = tmp_path / "api-error-test.db"
    application = create_app()
    try:
        with TestClient(application) as client:
            response = client.post(
                "/api/analysis/import/json",
                files={"file": ("bad.json", b"{broken", "application/json")},
            )
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "INVALID_JSON"
            assert response.json()["detail"]["analysis_run_id"].startswith("RUN-")
    finally:
        get_settings.cache_clear()
