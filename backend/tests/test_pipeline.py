import json
from pathlib import Path
from time import sleep
from typing import Type

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError
from app.main import create_app
from app.models import AnalysisRunStatus, EvidenceStance
from tests.test_evidence import EvidenceMockProvider
from tests.test_product_planning import ProductMockProvider
from tests.test_semantic import DynamicMockProvider


TERMINAL = {
    "COMPLETED",
    "COMPLETED_WITH_WARNINGS",
    "FAILED",
    "VALIDATION_FAILED",
}


class FullPipelineMockProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-full-pipeline-model"

    def __init__(self) -> None:
        self.semantic = DynamicMockProvider()
        self.evidence = EvidenceMockProvider(
            {f"R{index:06d}": EvidenceStance.SUPPORTS for index in range(1, 30)}
        )
        self.product = ProductMockProvider()

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
    ) -> BaseModel:
        target = (
            self.semantic
            if schema_name
            in {"TopicDiscoveryOutput", "FindingCandidateOutput", "ConsolidatedAnalysisResult"}
            else self.evidence
            if schema_name == "EvidenceJudgmentOutput"
            else self.product
        )
        return target.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            schema_name=schema_name,
        )


class PipelineFailureProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-failure-model"

    def generate_structured(self, **_: object) -> BaseModel:
        raise LLMProviderError("LLM_PROVIDER_ERROR", "Provider unavailable.")


class CorruptingProductService:
    def __init__(self, delegate, store) -> None:
        self.delegate = delegate
        self.store = store

    def generate(self, analysis_run_id: str):
        result = self.delegate.generate(analysis_run_id)
        test_case = result.product_planning.test_cases[0]
        result.product_planning.test_cases[0] = test_case.model_copy(
            update={"source_review_ids": ["R999999"]}
        )
        self.store.save(result)
        return result


def settings(tmp_path: Path, *, retries: int = 0) -> Settings:
    return Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "pipeline.db",
        llm_provider="mock-runtime-llm",
        llm_model="mock-full-pipeline-model",
        llm_review_batch_size=4,
        llm_max_retries=retries,
        evidence_batch_size=20,
    )


def upload_music_csv(client: TestClient) -> str:
    rows = ["id,text,rating,version,language"]
    feedback = [
        "Downloaded albums disappear when I go offline.",
        "Offline playback stops after a few seconds.",
        "Lyrics are out of sync with the music.",
        "The lyric view jumps to the wrong line.",
        "Collaborative playlists lose my friend's edits.",
        "Playlist changes do not synchronize.",
        "Recommendations repeat the same artists every day.",
        "The discovery mix ignores my listening history.",
    ]
    for index, text in enumerate(feedback, start=1):
        rows.append(f'M{index:03d},"{text}",2,9.1,en-US')
    response = client.post(
        "/api/analysis/import/csv",
        files={"file": ("music.csv", "\n".join(rows).encode("utf-8"), "text/csv")},
        data={
            "analysis_goal": "Prioritize offline playback, lyrics, playlists, and recommendations.",
            "output_language": "en-US",
        },
    )
    assert response.status_code == 200
    return response.json()["analysis_run_id"]


def wait_for_terminal(client: TestClient, run_id: str) -> dict:
    payload = {}
    for _ in range(300):
        payload = client.get(f"/api/analysis/{run_id}").json()
        if payload["run"]["status"] in TERMINAL:
            return payload
        sleep(0.01)
    raise AssertionError(f"Run did not finish: {json.dumps(payload)}")


def test_one_start_executes_the_complete_unknown_csv_pipeline(tmp_path: Path) -> None:
    provider = FullPipelineMockProvider()
    app = create_app(
        settings=settings(tmp_path),
        semantic_provider_factory=lambda _: provider,
    )
    with TestClient(app) as client:
        run_id = upload_music_csv(client)
        queued = client.post(
            f"/api/analysis/{run_id}/pipeline",
            json={"output_language": "en-US", "ui_language": "en-US"},
        )
        assert queued.status_code == 202
        payload = wait_for_terminal(client, run_id)
        assert payload["run"]["status"] == "COMPLETED_WITH_WARNINGS"
        assert payload["run"]["last_successful_stage"] == "TRACEABILITY_VALIDATION"
        assert payload["run"]["progress"] == 100
        assert payload["semantic_analysis"]["topic_count"] == 1
        assert payload["evidence_validation"]["finding_count"] == 1
        assert payload["product_planning"]["requirement_count"] == 1
        assert payload["product_planning"]["test_case_count"] == 1
        workspace = client.get(f"/api/analysis/{run_id}/workspace")
        assert workspace.status_code == 200
        assert workspace.json()["analysis_run_id"] == run_id
        assert len(workspace.json()["reviews"]) == 8
        trace = client.get(f"/api/analysis/{run_id}/traceability").json()
        assert trace["traceability"]["coverage"]["hard_failures"] == []
        assert trace["traceability"]["coverage"]["overall_traceability_coverage"] == 1
        assert trace["traceability"]["forward"]
        assert trace["traceability"]["reverse"]
        stages = {
            event["stage"]
            for event in trace["audit_events"]
            if event["event_type"] == "STAGE_COMPLETED"
        }
        assert {
            "DATA_ACQUISITION",
            "CLEANING_AND_NORMALIZATION",
            "TOPIC_CONSOLIDATION",
            "FINDING_FINALIZATION",
            "TEST_CASE_GENERATION",
            "TRACEABILITY_VALIDATION",
        }.issubset(stages)


def test_final_traceability_failure_sets_validation_failed(tmp_path: Path) -> None:
    provider = FullPipelineMockProvider()
    app = create_app(
        settings=settings(tmp_path),
        semantic_provider_factory=lambda _: provider,
    )
    app.state.full_pipeline_service.product_service = CorruptingProductService(
        app.state.product_planning_service,
        app.state.run_store,
    )
    with TestClient(app) as client:
        run_id = upload_music_csv(client)
        assert client.post(
            f"/api/analysis/{run_id}/pipeline",
            json={"output_language": "en-US", "ui_language": "en-US"},
        ).status_code == 202
        payload = wait_for_terminal(client, run_id)
        assert payload["run"]["status"] == "VALIDATION_FAILED"
        assert payload["run"]["error_code"] == "FINAL_TRACEABILITY_VALIDATION_FAILED"
        assert payload["run"]["last_successful_stage"] == "TEST_CASE_GENERATION"
        trace = client.get(f"/api/analysis/{run_id}/traceability").json()
        assert trace["traceability"]["coverage"]["hard_failures"]


def test_model_failure_preserves_cleaned_reviews_and_no_final_artifacts(tmp_path: Path) -> None:
    provider = PipelineFailureProvider()
    app = create_app(
        settings=settings(tmp_path, retries=0),
        semantic_provider_factory=lambda _: provider,
    )
    with TestClient(app) as client:
        run_id = upload_music_csv(client)
        assert client.post(
            f"/api/analysis/{run_id}/pipeline",
            json={"output_language": "en-US", "ui_language": "en-US"},
        ).status_code == 202
        payload = wait_for_terminal(client, run_id)
        assert payload["run"]["status"] == AnalysisRunStatus.FAILED.value
        assert payload["run"]["last_successful_stage"] == "CLEANING_AND_NORMALIZATION"
        reviews = client.get(f"/api/analysis/{run_id}/reviews").json()["reviews"]
        assert len(reviews) == 8
        trace = client.get(f"/api/analysis/{run_id}/traceability").json()
        assert trace["traceability"] is None
        assert any(event["event_type"] == "ERROR" for event in trace["audit_events"])
