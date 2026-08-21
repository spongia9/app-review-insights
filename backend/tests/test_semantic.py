import json
from time import sleep
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Type

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
    ConsolidationCheckpoint,
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
    repair_consolidation_lineage,
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
        all_topic_review_ids = payload["allowed_topic_review_ids"]
        all_finding_review_ids = payload["allowed_finding_review_ids"]
        all_batch_ids = list(
            dict.fromkeys(
                payload["review_to_batch"][review_id]
                for review_id in all_finding_review_ids
            )
        )
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
                    review_ids=all_topic_review_ids,
                    batch_id=payload["review_to_batch"][all_topic_review_ids[0]],
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
                    supporting_review_ids=all_finding_review_ids,
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


def service(
    tmp_path: Path,
    provider: LLMProvider,
    *,
    batch_size: int = 2,
    retries: int = 2,
    group_size: int = 4,
    reviews: Optional[List[Review]] = None,
) -> SemanticAnalysisService:
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "semantic-tests.db",
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
        llm_review_batch_size=batch_size,
        llm_consolidation_group_size=group_size,
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
    if reviews is not None:
        store.save(stored_result(reviews))
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


def test_deterministic_lineage_repair_carries_forward_missing_source_candidates() -> None:
    first_batch = BatchAnalysisResult(
        analysis_run_id=RUN_ID,
        batch_id="B0001",
        review_ids=["R000001"],
        topic_candidates=[
            TopicCandidate(
                id="T1",
                analysis_run_id=RUN_ID,
                name="Playback",
                summary="Playback",
                review_ids=["R000001"],
                batch_id="B0001",
            )
        ],
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
        topic_candidates=[
            TopicCandidate(
                id="T2",
                analysis_run_id=RUN_ID,
                name="Notifications",
                summary="Notifications",
                review_ids=["R000002"],
                batch_id="B0002",
            )
        ],
        finding_candidates=[
            FindingCandidate(
                id="F2",
                analysis_run_id=RUN_ID,
                topic="Notifications",
                title="Duplicate alerts",
                problem="Duplicate alerts",
                summary="Duplicate alerts",
                supporting_review_ids=["R000002"],
                source_batch_ids=["B0002"],
            )
        ],
    )
    source_units = [
        ConsolidatedAnalysisResult(
            analysis_run_id=RUN_ID,
            topic_candidates=batch.topic_candidates,
            finding_candidates=batch.finding_candidates,
        )
        for batch in (first_batch, second_batch)
    ]
    incomplete = ConsolidatedAnalysisResult(
        analysis_run_id=RUN_ID,
        topic_candidates=first_batch.topic_candidates,
        finding_candidates=first_batch.finding_candidates,
    )

    repaired = repair_consolidation_lineage(
        incomplete,
        source_units,
        {"R000001": "B0001", "R000002": "B0002"},
    )

    assert {
        review_id
        for topic in repaired.topic_candidates
        for review_id in topic.review_ids
    } == {"R000001", "R000002"}
    assert {
        review_id
        for finding in repaired.finding_candidates
        for review_id in finding.supporting_review_ids
    } == {"R000001", "R000002"}
    assert any(topic.name == "Notifications" for topic in repaired.topic_candidates)


def test_consolidation_repair_removes_out_of_group_ids_and_carries_source_lineage() -> None:
    source = ConsolidatedAnalysisResult(
        analysis_run_id=RUN_ID,
        topic_candidates=[
            TopicCandidate(
                id="T-SOURCE",
                analysis_run_id=RUN_ID,
                name="Offline playback",
                summary="Downloads fail offline.",
                review_ids=["R000001", "R000002"],
                batch_id="B0001",
            )
        ],
        finding_candidates=[
            FindingCandidate(
                id="F-SOURCE",
                analysis_run_id=RUN_ID,
                topic="Offline playback",
                title="Downloads fail offline",
                problem="Downloaded media is unavailable without a network.",
                summary="Two Reviews report the same problem.",
                supporting_review_ids=["R000001", "R000002"],
                source_batch_ids=["B0001"],
            )
        ],
    )
    invalid = ConsolidatedAnalysisResult(
        analysis_run_id=RUN_ID,
        topic_candidates=[
            TopicCandidate(
                id="T-MODEL",
                analysis_run_id=RUN_ID,
                name="Offline access",
                summary="Offline access is unreliable.",
                review_ids=["R000001", "R999999"],
                batch_id="B9999",
            )
        ],
        finding_candidates=[
            FindingCandidate(
                id="F-MODEL",
                analysis_run_id=RUN_ID,
                topic="Offline access",
                title="Offline downloads fail",
                problem="Downloaded media cannot play offline.",
                summary="The valid source Review reports failure.",
                supporting_review_ids=["R000001", "R999999"],
                source_batch_ids=["B9999"],
            )
        ],
    )

    repaired = repair_consolidation_lineage(
        invalid,
        [source],
        {"R000001": "B0001", "R000002": "B0001"},
    )

    serialized = repaired.model_dump_json()
    assert "R999999" not in serialized
    assert {
        review_id
        for candidate in repaired.finding_candidates
        for review_id in candidate.supporting_review_ids
    } == {"R000001", "R000002"}
    assert all(candidate.source_batch_ids == ["B0001"] for candidate in repaired.finding_candidates)


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


def test_hierarchical_consolidation_bounds_group_size_and_preserves_all_ids(tmp_path: Path) -> None:
    provider = DynamicMockProvider()
    reviews = [
        review(f"R{index:06d}", f"Review problem {index}")
        for index in range(1, 11)
    ]
    semantic_service = service(
        tmp_path,
        provider,
        batch_size=1,
        group_size=4,
        reviews=reviews,
    )

    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )

    semantic = completed.semantic_analysis
    assert semantic is not None
    assert semantic.consolidation_checkpoint is not None
    assert semantic.consolidation_checkpoint.round_number == 2
    assert len(semantic.consolidation_checkpoint.units) == 1
    consolidation_calls = [
        payload
        for schema_name, payload in provider.calls
        if schema_name == "ConsolidatedAnalysisResult"
    ]
    assert len(consolidation_calls) == 4
    assert max(len(payload["source_results"]) for payload in consolidation_calls) <= 4
    assert semantic.consolidated_result is not None
    assert semantic.consolidated_result.finding_candidates[0].supporting_review_ids == [
        review.id for review in reviews
    ]


def test_200_plus_reviews_consolidate_repeated_batch_topics_without_lineage_loss(tmp_path: Path) -> None:
    provider = DynamicMockProvider()
    reviews = [
        review(f"R{index:06d}", f"Advertisement interruption problem {index}")
        for index in range(1, 206)
    ]
    semantic_service = service(
        tmp_path,
        provider,
        batch_size=25,
        group_size=4,
        reviews=reviews,
    )

    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )

    semantic = completed.semantic_analysis
    assert semantic is not None
    assert semantic.batch_count == 9
    assert semantic.analyzed_review_count == 205
    assert semantic.consolidated_result is not None
    assert len(semantic.consolidated_result.topic_candidates) == 1
    assert len(semantic.consolidated_result.finding_candidates) == 1
    assert semantic.consolidated_result.topic_candidates[0].review_ids == [
        item.id for item in reviews
    ]
    assert semantic.consolidated_result.finding_candidates[0].supporting_review_ids == [
        item.id for item in reviews
    ]


def test_failed_consolidation_resumes_without_reanalyzing_batches(tmp_path: Path) -> None:
    original_provider = DynamicMockProvider()
    reviews = [
        review(f"R{index:06d}", f"Review problem {index}")
        for index in range(1, 11)
    ]
    semantic_service = service(
        tmp_path,
        original_provider,
        batch_size=1,
        group_size=4,
        reviews=reviews,
    )
    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    assert completed.semantic_analysis is not None
    failed_semantic = completed.semantic_analysis.model_copy(
        update={
            "consolidated_result": None,
            "consolidation_checkpoint": None,
            "analysis_time": None,
        }
    )
    failed_run = completed.run.model_copy(
        update={
            "status": AnalysisRunStatus.FAILED,
            "current_stage": PipelineStage.TOPIC_CONSOLIDATION,
            "last_successful_stage": PipelineStage.FINDING_EXTRACTION,
            "progress": 92,
            "errors": ["Prior consolidation failed."],
        }
    )
    semantic_service.store.save(
        completed.model_copy(
            update={"run": failed_run, "semantic_analysis": failed_semantic}
        )
    )

    resume_provider = DynamicMockProvider()
    resumed_service = SemanticAnalysisService(
        semantic_service.settings,
        semantic_service.store,
        provider_factory=lambda _: resume_provider,
    )
    queued = resumed_service.queue(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    assert queued.run.current_stage == PipelineStage.TOPIC_CONSOLIDATION
    assert queued.run.progress == 92
    assert queued.semantic_analysis is not None

    resumed = resumed_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    assert resumed.run.status == AnalysisRunStatus.COMPLETED
    assert resumed.semantic_analysis is not None
    assert resumed.semantic_analysis.consolidated_result is not None
    assert {
        schema_name for schema_name, _ in resume_provider.calls
    } == {"ConsolidatedAnalysisResult"}
    assert len(resume_provider.calls) == 4


def test_resume_uses_latest_completed_consolidation_round(tmp_path: Path) -> None:
    original_provider = DynamicMockProvider()
    reviews = [
        review(f"R{index:06d}", f"Review problem {index}")
        for index in range(1, 11)
    ]
    semantic_service = service(
        tmp_path,
        original_provider,
        batch_size=1,
        group_size=4,
        reviews=reviews,
    )
    completed = semantic_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    assert completed.semantic_analysis is not None
    first_round_artifacts = [
        artifact
        for artifact in completed.semantic_analysis.audit_artifacts
        if artifact.batch_id and artifact.batch_id.startswith("C-R01-")
    ]
    assert len(first_round_artifacts) == 3
    checkpoint = ConsolidationCheckpoint(
        analysis_run_id=RUN_ID,
        round_number=1,
        units=[
            ConsolidatedAnalysisResult.model_validate(artifact.payload)
            for artifact in first_round_artifacts
        ],
    )
    partial_semantic = completed.semantic_analysis.model_copy(
        update={
            "consolidated_result": None,
            "consolidation_checkpoint": checkpoint,
            "analysis_time": None,
        }
    )
    failed_run = completed.run.model_copy(
        update={
            "status": AnalysisRunStatus.FAILED,
            "current_stage": PipelineStage.TOPIC_CONSOLIDATION,
            "last_successful_stage": PipelineStage.TOPIC_CONSOLIDATION,
            "progress": 94,
            "errors": ["Final consolidation failed."],
        }
    )
    semantic_service.store.save(
        completed.model_copy(
            update={"run": failed_run, "semantic_analysis": partial_semantic}
        )
    )

    resume_provider = DynamicMockProvider()
    resumed_service = SemanticAnalysisService(
        semantic_service.settings,
        semantic_service.store,
        provider_factory=lambda _: resume_provider,
    )
    resumed_service.queue(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )
    resumed = resumed_service.analyze(
        RUN_ID,
        output_language=AnalysisOutputLanguage.EN_US,
        ui_language="en-US",
    )

    assert resumed.run.status == AnalysisRunStatus.COMPLETED
    assert len(resume_provider.calls) == 1
    assert resume_provider.calls[0][0] == "ConsolidatedAnalysisResult"
    assert len(resume_provider.calls[0][1]["source_results"]) == 3


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
    assert persisted.run.error_code == code
    assert persisted.run.last_successful_stage == PipelineStage.CLEANING_AND_NORMALIZATION
    assert len(persisted.reviews) == 3
    assert persisted.semantic_analysis is None
    assert persisted.run.errors[-1] == message
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


def test_invalid_api_key_failure_preserves_clean_reviews_without_fake_results(tmp_path: Path) -> None:
    provider = FailureProvider(
        LLMProviderError(
            "LLM_AUTHENTICATION_FAILED",
            "The LLM provider rejected the configured credentials with HTTP 401.",
            retryable=False,
        )
    )
    semantic_service = service(tmp_path, provider, retries=3)

    with pytest.raises(SemanticAnalysisError) as error:
        semantic_service.analyze(
            RUN_ID,
            output_language=AnalysisOutputLanguage.EN_US,
            ui_language="en-US",
        )

    assert error.value.code == "LLM_AUTHENTICATION_FAILED"
    assert provider.call_count == 1
    persisted = semantic_service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status == AnalysisRunStatus.FAILED
    assert persisted.run.error_code == "LLM_AUTHENTICATION_FAILED"
    assert persisted.run.last_successful_stage == PipelineStage.CLEANING_AND_NORMALIZATION
    assert len(persisted.reviews) == 3
    assert persisted.semantic_analysis is None
    assert persisted.run.errors == [
        "The LLM provider rejected the configured credentials with HTTP 401."
    ]


def test_truncated_output_is_not_retried_unchanged(tmp_path: Path) -> None:
    provider = FailureProvider(
        LLMProviderError(
            "LLM_OUTPUT_TRUNCATED",
            "The output reached its limit.",
            retryable=False,
            details={"finish_reason": "length", "completion_tokens": 4096},
        )
    )
    semantic_service = service(tmp_path, provider, retries=3)

    with pytest.raises(SemanticAnalysisError) as error:
        semantic_service.analyze(
            RUN_ID,
            output_language=AnalysisOutputLanguage.EN_US,
            ui_language="en-US",
        )

    assert error.value.code == "LLM_OUTPUT_TRUNCATED"
    assert provider.call_count == 1
    persisted = semantic_service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.error_code == "LLM_OUTPUT_TRUNCATED"
    assert "finish_reason" in persisted.run.revisions[-1]


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
    assert "R999999" not in completed.model_dump_json()


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

    class UnauthorizedClient(TimeoutClient):
        def post(self, *_: object, **__: object) -> object:
            request = __import__("httpx").Request("POST", "https://api.deepseek.com/chat/completions")
            return __import__("httpx").Response(401, request=request)

    monkeypatch.setattr("app.llm.deepseek.httpx.Client", UnauthorizedClient)
    with pytest.raises(LLMProviderError) as unauthorized_error:
        provider.generate_structured(
            system_prompt="json",
            user_prompt="{}",
            response_model=TopicDiscoveryOutput,
            schema_name="TopicDiscoveryOutput",
        )
    assert unauthorized_error.value.code == "LLM_AUTHENTICATION_FAILED"
    assert unauthorized_error.value.retryable is False
    assert "401" in unauthorized_error.value.message

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
    assert invalid_error.value.code == "LLM_INVALID_JSON"

    class TruncatedResponse(Response):
        def json(self) -> dict:
            return {
                "id": "response-truncated",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"topics": ['},
                    }
                ],
                "usage": {"prompt_tokens": 500, "completion_tokens": 1024},
            }

    class TruncatedClient(TimeoutClient):
        def post(self, *_: object, **__: object) -> TruncatedResponse:
            return TruncatedResponse()

    monkeypatch.setattr("app.llm.deepseek.httpx.Client", TruncatedClient)
    with pytest.raises(LLMProviderError) as truncated_error:
        provider.generate_structured(
            system_prompt="json",
            user_prompt="{}",
            response_model=TopicDiscoveryOutput,
            schema_name="TopicDiscoveryOutput",
        )
    assert truncated_error.value.code == "LLM_OUTPUT_TRUNCATED"
    assert truncated_error.value.retryable is False
    assert truncated_error.value.details["finish_reason"] == "length"
    assert truncated_error.value.details["completion_tokens"] == 1024

    class InvalidSchemaResponse(Response):
        def json(self) -> dict:
            return {
                "id": "response-schema",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"topics": [{"id": "missing-fields"}]}'},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }

    class InvalidSchemaClient(TimeoutClient):
        def post(self, *_: object, **__: object) -> InvalidSchemaResponse:
            return InvalidSchemaResponse()

    monkeypatch.setattr("app.llm.deepseek.httpx.Client", InvalidSchemaClient)
    with pytest.raises(LLMProviderError) as schema_error:
        provider.generate_structured(
            system_prompt="json",
            user_prompt="{}",
            response_model=TopicDiscoveryOutput,
            schema_name="TopicDiscoveryOutput",
        )
    assert schema_error.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert schema_error.value.details["validation_errors"]


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
