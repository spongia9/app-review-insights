import json
from time import sleep
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Type

import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError
from app.llm.deepseek import DeepSeekProvider
from app.models import (
    AnalysisOutputLanguage,
    AnalysisRun,
    AnalysisRunStatus,
    BatchAnalysisResult,
    CandidateStatus,
    ConsolidatedAnalysisResult,
    FindingCandidate,
    FindingCandidateOutput,
    IngestionResult,
    PipelineStage,
    ProviderMetadata,
    Review,
    SourceType,
    TopicCandidate,
    TopicDiscoveryOutput,
)
from app.services.semantic import (
    SemanticAnalysisError,
    SemanticAnalysisService,
    _validate_finding_scope,
    _validate_topic_scope,
    create_review_batches,
    resolve_output_language,
    validate_consolidation_lineage,
)
from app.storage import RunStore
from app.main import create_app
from fastapi.testclient import TestClient


RUN_ID = "RUN-SEMANTIC-001"


def review(review_id: str, text: str, language: str = "en-US", run_id: str = RUN_ID) -> Review:
    return Review(
        id=review_id,
        analysis_run_id=run_id,
        source="test_fixture",
        rating=2,
        title="User feedback",
        text=text,
        version="3.1",
        language=language,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def stored_result(reviews: List[Review]) -> IngestionResult:
    return IngestionResult(
        analysis_run_id=RUN_ID,
        run=AnalysisRun(
            id=RUN_ID,
            source_type=SourceType.JSON,
            analysis_goal="Identify the most disruptive listening problems",
            status=AnalysisRunStatus.COMPLETED,
            current_stage=PipelineStage.CLEANING_AND_NORMALIZATION,
            last_successful_stage=PipelineStage.CLEANING_AND_NORMALIZATION,
            progress=100,
            total_review_count=len(reviews),
        ),
        provider=ProviderMetadata(
            analysis_run_id=RUN_ID,
            source="json_upload",
            collection_time=datetime.now(timezone.utc),
        ),
        reviews=reviews,
    )


class DynamicMockProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-semantic-model"

    def __init__(self) -> None:
        self.calls = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
    ) -> BaseModel:
        payload = json.loads(user_prompt)
        self.calls.append((schema_name, payload))
        language = payload["output_language"]
        if schema_name == "TopicDiscoveryOutput":
            batch_id = payload["batch_id"]
            ids = payload["allowed_review_ids"]
            name = "离线下载与播放可靠性" if language == "zh-CN" else "Offline download and playback reliability"
            return TopicDiscoveryOutput(
                topics=[
                    TopicCandidate(
                        id=f"T-{batch_id}",
                        analysis_run_id=payload["analysis_run_id"],
                        name=name,
                        summary=name,
                        review_ids=ids,
                        batch_id=batch_id,
                    )
                ]
            )
        if schema_name == "FindingCandidateOutput":
            batch_id = payload["batch_id"]
            ids = payload["allowed_review_ids"]
            text = "下载内容在离线状态下可能无法播放" if language == "zh-CN" else "Downloaded episodes may fail to play offline"
            return FindingCandidateOutput(
                finding_candidates=[
                    FindingCandidate(
                        id=f"FC-{batch_id}",
                        analysis_run_id=payload["analysis_run_id"],
                        topic=payload["topics"][0]["name"],
                        title=text,
                        problem=text,
                        summary=text,
                        supporting_review_ids=ids,
                        source_batch_ids=[batch_id],
                    )
                ]
            )
        batch_results = payload["batch_results"]
        all_review_ids = list(dict.fromkeys(review_id for batch in batch_results for review_id in batch["review_ids"]))
        all_batch_ids = [batch["batch_id"] for batch in batch_results]
        name = "离线下载与播放可靠性" if language == "zh-CN" else "Offline download and playback reliability"
        text = "下载内容在离线状态下可能无法播放" if language == "zh-CN" else "Downloaded episodes may fail to play offline"
        return ConsolidatedAnalysisResult(
            analysis_run_id=payload["analysis_run_id"],
            topic_candidates=[
                TopicCandidate(
                    id="T-GLOBAL-001",
                    analysis_run_id=payload["analysis_run_id"],
                    name=name,
                    summary=name,
                    review_ids=all_review_ids,
                    batch_id=all_batch_ids[0],
                )
            ],
            finding_candidates=[
                FindingCandidate(
                    id="FC-GLOBAL-001",
                    analysis_run_id=payload["analysis_run_id"],
                    topic=name,
                    title=text,
                    problem=text,
                    summary=text,
                    supporting_review_ids=all_review_ids,
                    source_batch_ids=all_batch_ids,
                )
            ],
        )


class FailureProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-semantic-model"

    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.call_count = 0

    def generate_structured(self, **_: object) -> BaseModel:
        self.call_count += 1
        raise self.error


class CorrectingInvalidIdProvider(DynamicMockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.topic_attempts = 0

    def generate_structured(self, **kwargs: object) -> BaseModel:
        if kwargs["schema_name"] == "TopicDiscoveryOutput":
            self.topic_attempts += 1
            if self.topic_attempts == 1:
                payload = json.loads(str(kwargs["user_prompt"]))
                return TopicDiscoveryOutput(
                    topics=[
                        TopicCandidate(
                            id="T-BAD",
                            analysis_run_id=payload["analysis_run_id"],
                            name="Invalid reference",
                            summary="Invalid reference",
                            review_ids=["R999999"],
                            batch_id=payload["batch_id"],
                        )
                    ]
                )
        return super().generate_structured(**kwargs)  # type: ignore[arg-type]


def service(tmp_path: Path, provider: LLMProvider, *, batch_size: int = 2, retries: int = 2) -> SemanticAnalysisService:
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "semantic-tests.db",
        llm_review_batch_size=batch_size,
        llm_max_retries=retries,
    )
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    store.save(
        stored_result(
            [
                review("R000001", "Downloaded episodes disappear when airplane mode is enabled."),
                review("R000002", "离线缓存完成后仍然无法播放。", "zh-CN"),
                review("R000003", "The transcript loses sync after changing playback speed."),
            ]
        )
    )
    return SemanticAnalysisService(settings, store, provider_factory=lambda _: provider)


def test_batch_creation_and_batch_size() -> None:
    batches = create_review_batches([review(f"R{index:06d}", "text") for index in range(1, 6)], 2)
    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_structured_topic_and_finding_candidate_parsing() -> None:
    topic = TopicCandidate.model_validate(
        {
            "id": "T001",
            "analysis_run_id": RUN_ID,
            "name": "Playback queue ordering",
            "summary": "Queue order changes unexpectedly.",
            "review_ids": ["R000001"],
            "batch_id": "B0001",
        }
    )
    finding = FindingCandidate.model_validate(
        {
            "id": "FC001",
            "analysis_run_id": RUN_ID,
            "topic": topic.name,
            "title": "Queue order changes after adding an episode",
            "problem": "Users cannot preserve the intended playback order.",
            "summary": "The queue is reordered after new items are added.",
            "supporting_review_ids": ["R000001"],
            "source_batch_ids": ["B0001"],
        }
    )
    assert finding.candidate_status == CandidateStatus.UNVALIDATED_CANDIDATE
    with pytest.raises(ValidationError):
        TopicCandidate.model_validate({**topic.model_dump(), "review_ids": ["R000001", "R000001"]})


def test_batch_allowlist_rejects_invalid_review_id() -> None:
    topic = TopicCandidate(
        id="T001",
        analysis_run_id=RUN_ID,
        name="Topic",
        summary="Summary",
        review_ids=["R999999"],
        batch_id="B0001",
    )
    with pytest.raises(SemanticAnalysisError, match="R999999"):
        _validate_topic_scope(
            [topic],
            analysis_run_id=RUN_ID,
            allowed_review_ids={"R000001"},
            allowed_batch_ids={"B0001"},
        )


def test_analysis_run_isolation_rejects_cross_run_reference() -> None:
    finding = FindingCandidate(
        id="FC001",
        analysis_run_id="RUN-OTHER",
        topic="Topic",
        title="Title",
        problem="Problem",
        summary="Summary",
        supporting_review_ids=["R000001"],
        source_batch_ids=["B0001"],
    )
    with pytest.raises(SemanticAnalysisError, match="another analysis run"):
        _validate_finding_scope(
            [finding],
            analysis_run_id=RUN_ID,
            allowed_review_ids={"R000001"},
            allowed_batch_ids={"B0001"},
        )


def test_consolidation_must_preserve_lineage() -> None:
    batch = BatchAnalysisResult(
        analysis_run_id=RUN_ID,
        batch_id="B0001",
        review_ids=["R000001", "R000002"],
        topic_candidates=[
            TopicCandidate(
                id="T1",
                analysis_run_id=RUN_ID,
                name="Offline playback",
                summary="Offline playback",
                review_ids=["R000001", "R000002"],
                batch_id="B0001",
            )
        ],
        finding_candidates=[
            FindingCandidate(
                id="F1",
                analysis_run_id=RUN_ID,
                topic="Offline playback",
                title="Downloads fail offline",
                problem="Downloads fail offline",
                summary="Downloads fail offline",
                supporting_review_ids=["R000001", "R000002"],
                source_batch_ids=["B0001"],
            )
        ],
    )
    consolidated = ConsolidatedAnalysisResult(
        analysis_run_id=RUN_ID,
        topic_candidates=[batch.topic_candidates[0].model_copy(update={"review_ids": ["R000001"]})],
        finding_candidates=[batch.finding_candidates[0].model_copy(update={"supporting_review_ids": ["R000001"]})],
    )
    with pytest.raises(SemanticAnalysisError, match="dropped"):
        validate_consolidation_lineage(consolidated, [batch])


def test_consolidation_must_preserve_source_batch_lineage() -> None:
    first_batch = BatchAnalysisResult(
        analysis_run_id=RUN_ID,
        batch_id="B0001",
        review_ids=["R000001"],
        finding_candidates=[
            FindingCandidate(
                id="F1",
                analysis_run_id=RUN_ID,
                topic="Playback",
                title="Playback stops",
                problem="Playback stops",
                summary="Playback stops",
                supporting_review_ids=["R000001"],
                source_batch_ids=["B0001"],
            )
        ],
    )
    second_batch = BatchAnalysisResult(
        analysis_run_id=RUN_ID,
        batch_id="B0002",
        review_ids=["R000002"],
        finding_candidates=[
            FindingCandidate(
                id="F2",
                analysis_run_id=RUN_ID,
                topic="Playback",
                title="Playback stops",
                problem="Playback stops",
                summary="Playback stops",
                supporting_review_ids=["R000002"],
                source_batch_ids=["B0002"],
            )
        ],
    )
    consolidated = ConsolidatedAnalysisResult(
        analysis_run_id=RUN_ID,
        finding_candidates=[
            first_batch.finding_candidates[0].model_copy(
                update={
                    "supporting_review_ids": ["R000001", "R000002"],
                    "source_batch_ids": ["B0001"],
                }
            )
        ],
    )

    with pytest.raises(SemanticAnalysisError, match="Review-to-batch lineage"):
        validate_consolidation_lineage(consolidated, [first_batch, second_batch])


def test_multilingual_unknown_domain_and_output_language_propagation(tmp_path: Path) -> None:
    provider = DynamicMockProvider()
    semantic_service = service(tmp_path, provider, batch_size=2)
    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.ZH_CN,
        ui_language="en-US",
    )
    semantic = completed.semantic_analysis
    assert semantic is not None
    assert semantic.total_review_count == semantic.analyzed_review_count == 3
    assert semantic.batch_count == 2
    assert semantic.sampling_strategy == "NONE"
    assert semantic.resolved_output_language == AnalysisOutputLanguage.ZH_CN
    assert semantic.consolidated_result is not None
    assert semantic.consolidated_result.topic_candidates[0].name == "离线下载与播放可靠性"
    assert semantic.consolidated_result.finding_candidates[0].supporting_review_ids == [
        "R000001",
        "R000002",
        "R000003",
    ]
    assert all(call[1]["analysis_goal"] for call in provider.calls)
    assert all(call[1]["output_language"] == "zh-CN" for call in provider.calls)
    assert all("raw_data" not in json.dumps(call[1]) for call in provider.calls)


def test_follow_ui_output_language_resolution() -> None:
    assert resolve_output_language(AnalysisOutputLanguage.FOLLOW_UI, "en-US") == AnalysisOutputLanguage.EN_US
    assert resolve_output_language(AnalysisOutputLanguage.FOLLOW_UI, "zh-CN") == AnalysisOutputLanguage.ZH_CN
    assert resolve_output_language(AnalysisOutputLanguage.ZH_CN, "en-US") == AnalysisOutputLanguage.ZH_CN


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("LLM_TIMEOUT", "The LLM request timed out."),
        ("INVALID_STRUCTURED_OUTPUT", "The model returned invalid JSON."),
    ],
)
def test_provider_failures_respect_retry_limit(tmp_path: Path, code: str, message: str) -> None:
    provider = FailureProvider(LLMProviderError(code, message))
    semantic_service = service(tmp_path, provider, retries=2)
    with pytest.raises(SemanticAnalysisError) as error:
        semantic_service.analyze(
            RUN_ID,
            output_language=AnalysisOutputLanguage.EN_US,
            ui_language="en-US",
        )
    assert error.value.code == code
    assert provider.call_count == 3
    persisted = semantic_service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status == AnalysisRunStatus.FAILED
    assert persisted.run.last_successful_stage == PipelineStage.CLEANING_AND_NORMALIZATION
    assert len(persisted.run.revisions) == 3


def test_non_retryable_provider_configuration_error_stops_immediately(tmp_path: Path) -> None:
    provider = FailureProvider(
        LLMProviderError("LLM_NOT_CONFIGURED", "Missing API key.", retryable=False)
    )
    semantic_service = service(tmp_path, provider, retries=3)
    with pytest.raises(SemanticAnalysisError, match="Missing API key"):
        semantic_service.analyze(
            RUN_ID,
            output_language=AnalysisOutputLanguage.EN_US,
            ui_language="en-US",
        )
    assert provider.call_count == 1


def test_invalid_review_id_receives_correction_retry(tmp_path: Path) -> None:
    provider = CorrectingInvalidIdProvider()
    semantic_service = service(tmp_path, provider, batch_size=3, retries=1)
    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    assert completed.run.status == AnalysisRunStatus.COMPLETED
    assert provider.topic_attempts == 2
    assert any("INVALID_REVIEW_ID" in revision for revision in completed.run.revisions)


def test_deepseek_provider_timeout_and_invalid_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DeepSeekProvider(
        api_key="test-key",
        model_name="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        timeout_seconds=1,
        max_output_tokens=1024,
        temperature=0.2,
        thinking_enabled=False,
        trust_environment_proxy=False,
    )

    class TimeoutClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "TimeoutClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def post(self, *_: object, **__: object) -> None:
            raise __import__("httpx").TimeoutException("timeout")

    monkeypatch.setattr("app.llm.deepseek.httpx.Client", TimeoutClient)
    with pytest.raises(LLMProviderError) as timeout_error:
        provider.generate_structured(
            system_prompt="json",
            user_prompt="{}",
            response_model=TopicDiscoveryOutput,
            schema_name="TopicDiscoveryOutput",
        )
    assert timeout_error.value.code == "LLM_TIMEOUT"

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "not-json"}}]}

    class InvalidClient(TimeoutClient):
        def post(self, *_: object, **__: object) -> Response:
            return Response()

    monkeypatch.setattr("app.llm.deepseek.httpx.Client", InvalidClient)
    with pytest.raises(LLMProviderError) as invalid_error:
        provider.generate_structured(
            system_prompt="json",
            user_prompt="{}",
            response_model=TopicDiscoveryOutput,
            schema_name="TopicDiscoveryOutput",
        )
    assert invalid_error.value.code == "INVALID_STRUCTURED_OUTPUT"


def test_semantic_api_starts_polls_and_exposes_candidates(tmp_path: Path) -> None:
    provider = DynamicMockProvider()
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "semantic-api.db",
        llm_review_batch_size=2,
    )
    app = create_app(settings=settings, semantic_provider_factory=lambda _: provider)
    app.state.run_store.save(
        stored_result(
            [
                review("R000001", "Downloaded episodes disappear offline."),
                review("R000002", "离线缓存无法播放。", "zh-CN"),
            ]
        )
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/analysis/{RUN_ID}/semantic",
            json={"output_language": "en-US", "ui_language": "zh-CN"},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["run"]["status"] in {"PENDING", "RUNNING"}

        for _ in range(50):
            run_response = client.get(f"/api/analysis/{RUN_ID}")
            assert run_response.status_code == 200
            if run_response.json()["run"]["status"] in {"COMPLETED", "WARNING", "FAILED"}:
                break
            sleep(0.01)
        run_payload = run_response.json()
        assert run_payload["run"]["status"] == "COMPLETED"
        assert run_payload["semantic_analysis"]["topic_count"] == 1

        topics = client.get(f"/api/analysis/{RUN_ID}/topics").json()["topics"]
        findings = client.get(f"/api/analysis/{RUN_ID}/finding-candidates").json()["finding_candidates"]
        assert topics[0]["review_ids"] == ["R000001", "R000002"]
        assert findings[0]["candidate_status"] == "UNVALIDATED_CANDIDATE"
        assert findings[0]["supporting_review_ids"] == ["R000001", "R000002"]
