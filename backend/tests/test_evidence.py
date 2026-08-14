import json
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Dict, List, Optional, Type

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError
from app.main import create_app
from app.models import (
    AnalysisOutputLanguage,
    AnalysisRun,
    AnalysisRunStatus,
    ConsolidatedAnalysisResult,
    EvidenceJudgment,
    EvidenceJudgmentOutput,
    EvidenceStance,
    FindingCandidate,
    FindingEvidenceStatus,
    IngestionResult,
    PipelineStage,
    ProviderMetadata,
    Review,
    SemanticAnalysisResult,
    SourceType,
    TopicCandidate,
)
from app.services.evidence import (
    EvidenceValidationError,
    EvidenceValidationService,
    calculate_evidence_outcome,
    create_evidence_batches,
    normalize_judgments,
    validate_candidate_evidence_scope,
)
from app.storage import RunStore


RUN_ID = "RUN-EVIDENCE-001"


def review(review_id: str, text: str, *, run_id: str = RUN_ID, language: str = "en-US") -> Review:
    return Review(
        id=review_id,
        analysis_run_id=run_id,
        source="test_fixture",
        rating=3,
        title="Evidence fixture",
        text=text,
        version="4.2",
        language=language,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


def candidate(review_ids: List[str], *, run_id: str = RUN_ID) -> FindingCandidate:
    return FindingCandidate(
        id="FC-EVIDENCE-001",
        analysis_run_id=run_id,
        topic="Offline playback reliability",
        title="Offline downloads fail to play",
        problem="Users cannot reliably play downloaded content without a connection.",
        summary="Downloaded content may be unavailable while offline.",
        supporting_review_ids=review_ids,
        source_batch_ids=["B0001"],
    )


def phase3_result(
    reviews: List[Review],
    finding_candidate: FindingCandidate,
    *,
    run_id: str = RUN_ID,
    topic_review_ids: Optional[List[str]] = None,
    output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.EN_US,
) -> IngestionResult:
    topic_ids = topic_review_ids or [item.id for item in reviews]
    consolidated = ConsolidatedAnalysisResult(
        analysis_run_id=run_id,
        topic_candidates=[
            TopicCandidate(
                id="T-GLOBAL-001",
                analysis_run_id=run_id,
                name=finding_candidate.topic,
                summary="Model-derived topic evidence pool.",
                review_ids=topic_ids,
                batch_id="B0001",
            )
        ],
        finding_candidates=[finding_candidate],
    )
    semantic = SemanticAnalysisResult(
        analysis_run_id=run_id,
        total_review_count=len(reviews),
        analyzed_review_count=len(reviews),
        batch_count=1,
        batch_size=max(1, len(reviews)),
        model_provider="mock-runtime-llm",
        model_name="mock-semantic-model",
        output_language=output_language,
        resolved_output_language=output_language,
        consolidated_result=consolidated,
        analysis_time=datetime.now(timezone.utc),
    )
    return IngestionResult(
        analysis_run_id=run_id,
        run=AnalysisRun(
            id=run_id,
            source_type=SourceType.JSON,
            analysis_goal="Validate offline playback evidence",
            output_language=output_language,
            resolved_output_language=output_language,
            status=AnalysisRunStatus.COMPLETED,
            current_stage=PipelineStage.TOPIC_CONSOLIDATION,
            last_successful_stage=PipelineStage.TOPIC_CONSOLIDATION,
            progress=100,
            total_review_count=len(reviews),
            analyzed_review_count=len(reviews),
        ),
        provider=ProviderMetadata(
            analysis_run_id=run_id,
            source="json_upload",
            collection_time=datetime.now(timezone.utc),
        ),
        reviews=reviews,
        semantic_analysis=semantic,
    )


class EvidenceMockProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-evidence-model"

    def __init__(self, stances: Dict[str, EvidenceStance], *, relevance: float = 0.9) -> None:
        self.stances = stances
        self.relevance = relevance
        self.calls: List[Dict[str, object]] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
    ) -> BaseModel:
        assert schema_name == "EvidenceJudgmentOutput"
        payload = json.loads(user_prompt)
        self.calls.append(payload)
        reason = "该评论与候选主张的语义关系已验证。" if payload["output_language"] == "zh-CN" else "The semantic relationship to the candidate claim was validated."
        return EvidenceJudgmentOutput(
            analysis_run_id=payload["analysis_run_id"],
            finding_candidate_id=payload["finding_candidate_id"],
            judgments=[
                EvidenceJudgment(
                    analysis_run_id=payload["analysis_run_id"],
                    finding_candidate_id=payload["finding_candidate_id"],
                    review_id=review_id,
                    stance=self.stances[review_id],
                    semantic_relevance=self.relevance,
                    reason=reason,
                )
                for review_id in payload["allowed_review_ids"]
            ],
        )


class FailureProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-evidence-model"

    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.call_count = 0

    def generate_structured(self, **_: object) -> BaseModel:
        self.call_count += 1
        raise self.error


class InvalidIdProvider(EvidenceMockProvider):
    def generate_structured(self, **kwargs: object) -> BaseModel:
        self.calls.append(json.loads(str(kwargs["user_prompt"])))
        payload = self.calls[-1]
        return EvidenceJudgmentOutput(
            analysis_run_id=str(payload["analysis_run_id"]),
            finding_candidate_id=str(payload["finding_candidate_id"]),
            judgments=[
                EvidenceJudgment(
                    analysis_run_id=str(payload["analysis_run_id"]),
                    finding_candidate_id=str(payload["finding_candidate_id"]),
                    review_id="R999999",
                    stance=EvidenceStance.SUPPORTS,
                    semantic_relevance=0.99,
                    reason="Hallucinated identifier.",
                )
            ],
        )


def make_service(
    tmp_path: Path,
    result: IngestionResult,
    provider: LLMProvider,
    *,
    retries: int = 1,
    batch_size: int = 3,
) -> EvidenceValidationService:
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "evidence-tests.db",
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
        llm_max_retries=retries,
        evidence_batch_size=batch_size,
        evidence_conflict_pool_max_reviews=20,
        evidence_high_strength_min_count=5,
    )
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    store.save(result)
    return EvidenceValidationService(settings, store, provider_factory=lambda _: provider)


def judgments(stances: List[EvidenceStance], relevance: float = 0.9) -> List[EvidenceJudgment]:
    return [
        EvidenceJudgment(
            analysis_run_id=RUN_ID,
            finding_candidate_id="FC-EVIDENCE-001",
            review_id=f"R{index:06d}",
            stance=stance,
            semantic_relevance=relevance,
            reason="Fixture judgment.",
        )
        for index, stance in enumerate(stances, start=1)
    ]


def test_evidence_batch_creation_and_batch_size() -> None:
    batches = create_evidence_batches([review(f"R{index:06d}", "text") for index in range(1, 8)], 3)
    assert [len(batch) for batch in batches] == [3, 3, 1]


def test_stance_schema_and_duplicate_rejection() -> None:
    output = EvidenceJudgmentOutput(
        analysis_run_id=RUN_ID,
        finding_candidate_id="FC-EVIDENCE-001",
        judgments=judgments([EvidenceStance.SUPPORTS]),
    )
    assert output.judgments[0].stance is EvidenceStance.SUPPORTS
    with pytest.raises(ValidationError):
        EvidenceJudgmentOutput(
            analysis_run_id=RUN_ID,
            finding_candidate_id="FC-EVIDENCE-001",
            judgments=[output.judgments[0], output.judgments[0]],
        )
    with pytest.raises(ValidationError):
        EvidenceJudgment(
            analysis_run_id=RUN_ID,
            finding_candidate_id="FC-EVIDENCE-001",
            review_id="R000001",
            stance="PARTIAL_SUPPORT",
            semantic_relevance=0.8,
            reason="Invalid stance fixture.",
        )


@pytest.mark.parametrize(
    ("stances", "expected"),
    [
        ([EvidenceStance.SUPPORTS] * 5, FindingEvidenceStatus.SUPPORTED),
        ([EvidenceStance.SUPPORTS] * 2, FindingEvidenceStatus.WEAK),
        ([EvidenceStance.SUPPORTS], FindingEvidenceStatus.INSUFFICIENT),
        ([EvidenceStance.SUPPORTS] * 3 + [EvidenceStance.CONFLICTS] * 3, FindingEvidenceStatus.CONFLICTED),
        ([EvidenceStance.IRRELEVANT] * 4, FindingEvidenceStatus.UNSUPPORTED),
    ],
)
def test_status_rules(stances: List[EvidenceStance], expected: FindingEvidenceStatus) -> None:
    settings = Settings(_env_file=None, evidence_high_strength_min_count=5)
    metrics, status, confidence, _ = calculate_evidence_outcome(judgments(stances), settings)
    assert status is expected
    assert 0 <= confidence <= 1
    assert metrics.support_count == stances.count(EvidenceStance.SUPPORTS)
    assert metrics.conflict_count == stances.count(EvidenceStance.CONFLICTS)
    if expected is FindingEvidenceStatus.WEAK:
        assert confidence <= settings.evidence_weak_confidence_cap
    if expected is FindingEvidenceStatus.INSUFFICIENT:
        assert confidence <= settings.evidence_insufficient_confidence_cap
    if expected is FindingEvidenceStatus.UNSUPPORTED:
        assert confidence <= settings.evidence_unsupported_confidence_cap


@pytest.mark.parametrize(
    ("fixture_stances", "expected"),
    [
        ([EvidenceStance.SUPPORTS] * 5, FindingEvidenceStatus.SUPPORTED),
        ([EvidenceStance.SUPPORTS] * 2, FindingEvidenceStatus.WEAK),
        ([EvidenceStance.SUPPORTS] * 3 + [EvidenceStance.CONFLICTS] * 3, FindingEvidenceStatus.CONFLICTED),
        ([EvidenceStance.SUPPORTS], FindingEvidenceStatus.INSUFFICIENT),
        ([EvidenceStance.IRRELEVANT] * 3, FindingEvidenceStatus.UNSUPPORTED),
    ],
)
def test_five_acceptance_fixtures_persist_end_to_end(
    tmp_path: Path,
    fixture_stances: List[EvidenceStance],
    expected: FindingEvidenceStatus,
) -> None:
    reviews = [
        review(f"R{index:06d}", f"Acceptance evidence {index}")
        for index in range(1, len(fixture_stances) + 1)
    ]
    stance_map = {
        review_item.id: stance
        for review_item, stance in zip(reviews, fixture_stances)
    }
    item = candidate([review_item.id for review_item in reviews])
    service = make_service(
        tmp_path,
        phase3_result(reviews, item),
        EvidenceMockProvider(stance_map),
    )

    completed = service.validate(RUN_ID)

    evidence = completed.evidence_validation
    assert evidence is not None
    assert evidence.findings[0].status is expected
    assert evidence.audits[0].status is expected
    assert evidence.audits[0].finding_candidate_id == item.id


def test_low_relevance_support_is_reclassified_and_filtered() -> None:
    normalized, revisions = normalize_judgments(
        judgments([EvidenceStance.SUPPORTS], relevance=0.2), 0.55
    )
    assert normalized[0].stance is EvidenceStance.IRRELEVANT
    assert revisions


def test_support_conflict_neutral_and_irrelevant_reclassification(tmp_path: Path) -> None:
    reviews = [review(f"R{index:06d}", f"Review {index}") for index in range(1, 9)]
    candidate_item = candidate([item.id for item in reviews[:4]])
    stances = {
        "R000001": EvidenceStance.SUPPORTS,
        "R000002": EvidenceStance.SUPPORTS,
        "R000003": EvidenceStance.SUPPORTS,
        "R000004": EvidenceStance.SUPPORTS,
        "R000005": EvidenceStance.CONFLICTS,
        "R000006": EvidenceStance.CONFLICTS,
        "R000007": EvidenceStance.NEUTRAL,
        "R000008": EvidenceStance.IRRELEVANT,
    }
    provider = EvidenceMockProvider(stances)
    service = make_service(
        tmp_path,
        phase3_result(reviews, candidate_item, topic_review_ids=[item.id for item in reviews]),
        provider,
    )

    completed = service.validate(RUN_ID)

    assert completed.run.status is AnalysisRunStatus.WARNING
    finding = completed.evidence_validation.findings[0]  # type: ignore[union-attr]
    audit = completed.evidence_validation.audits[0]  # type: ignore[union-attr]
    assert finding.status is FindingEvidenceStatus.CONFLICTED
    assert finding.supporting_review_ids == ["R000001", "R000002", "R000003", "R000004"]
    assert finding.conflicting_review_ids == ["R000005", "R000006"]
    assert finding.support_count == 4
    assert finding.conflict_count == 2
    assert audit.neutral_review_ids == ["R000007"]
    assert audit.irrelevant_review_ids == ["R000008"]
    assert audit.candidate_review_ids == ["R000001", "R000002", "R000003", "R000004"]
    assert finding.validation_metadata.audit_id == audit.id


def test_unsupported_candidate_is_preserved_in_audit(tmp_path: Path) -> None:
    reviews = [review("R000001", "The review is about a different feature."), review("R000002", "Also unrelated.")]
    item = candidate([review_item.id for review_item in reviews])
    service = make_service(
        tmp_path,
        phase3_result(reviews, item),
        EvidenceMockProvider({review_item.id: EvidenceStance.IRRELEVANT for review_item in reviews}),
    )

    completed = service.validate(RUN_ID)

    evidence = completed.evidence_validation
    assert evidence is not None
    assert evidence.findings[0].status is FindingEvidenceStatus.UNSUPPORTED
    assert not evidence.findings[0].validation_metadata.eligible_for_requirement_generation
    assert evidence.audits[0].finding_candidate_id == item.id
    assert completed.semantic_analysis.consolidated_result.finding_candidates[0] == item  # type: ignore[union-attr]


def test_invalid_review_id_is_rejected_before_provider_call(tmp_path: Path) -> None:
    provider = EvidenceMockProvider({})
    item = candidate(["R999999"])
    service = make_service(
        tmp_path,
        phase3_result([review("R000001", "Current run")], item, topic_review_ids=["R000001"]),
        provider,
    )
    with pytest.raises(EvidenceValidationError) as raised:
        service.validate(RUN_ID)
    assert raised.value.code == "INVALID_REVIEW_ID"
    assert provider.calls == []


def test_cross_run_review_id_is_rejected(tmp_path: Path) -> None:
    provider = EvidenceMockProvider({})
    item = candidate(["RX-OTHER-RUN"])
    current = phase3_result(
        [review("R000001", "Current run")], item, topic_review_ids=["R000001"]
    )
    service = make_service(tmp_path, current, provider)
    other_review = review("RX-OTHER-RUN", "Other run", run_id="RUN-OTHER")
    other_candidate = candidate(["RX-OTHER-RUN"], run_id="RUN-OTHER")
    service.store.save(phase3_result([other_review], other_candidate, run_id="RUN-OTHER"))

    with pytest.raises(EvidenceValidationError) as raised:
        service.validate(RUN_ID)

    assert raised.value.code == "CROSS_RUN_REFERENCE"
    assert provider.calls == []


def test_output_hallucinated_id_retries_then_fails_without_saving_finding(tmp_path: Path) -> None:
    reviews = [review("R000001", "Offline playback fails.")]
    provider = InvalidIdProvider({"R000001": EvidenceStance.SUPPORTS})
    service = make_service(tmp_path, phase3_result(reviews, candidate(["R000001"])), provider, retries=1)

    with pytest.raises(EvidenceValidationError) as raised:
        service.validate(RUN_ID)

    assert raised.value.code == "INVALID_REVIEW_ID"
    assert len(provider.calls) == 2
    persisted = service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status is AnalysisRunStatus.FAILED
    assert persisted.evidence_validation is None
    assert "R999999" not in persisted.model_dump_json()


@pytest.mark.parametrize(
    "provider_error",
    [
        LLMProviderError("LLM_TIMEOUT", "Timed out."),
        LLMProviderError("LLM_PROVIDER_ERROR", "Provider unavailable."),
        LLMProviderError("LLM_INVALID_JSON", "Malformed structured output."),
    ],
)
def test_provider_failures_preserve_phase2_and_phase3(
    tmp_path: Path, provider_error: LLMProviderError
) -> None:
    reviews = [review("R000001", "Offline playback fails."), review("R000002", "Download is unavailable.")]
    provider = FailureProvider(provider_error)
    service = make_service(tmp_path, phase3_result(reviews, candidate([item.id for item in reviews])), provider, retries=1)

    with pytest.raises(EvidenceValidationError):
        service.validate(RUN_ID)

    persisted = service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status is AnalysisRunStatus.FAILED
    assert len(persisted.reviews) == 2
    assert persisted.semantic_analysis is not None
    assert persisted.semantic_analysis.consolidated_result is not None
    assert persisted.evidence_validation is None
    assert provider.call_count == 2


def test_multilingual_reviews_remain_unchanged_and_output_language_propagates(tmp_path: Path) -> None:
    reviews = [
        review("R000001", "Downloads fail in airplane mode.", language="en-US"),
        review("R000002", "离线缓存后仍然无法播放。", language="zh-CN"),
    ]
    original_text = [item.text for item in reviews]
    item = candidate([review_item.id for review_item in reviews])
    result = phase3_result(reviews, item, output_language=AnalysisOutputLanguage.ZH_CN)
    provider = EvidenceMockProvider({review_item.id: EvidenceStance.SUPPORTS for review_item in reviews})
    service = make_service(tmp_path, result, provider)

    completed = service.validate(RUN_ID)

    assert provider.calls[0]["output_language"] == "zh-CN"
    assert [item.text for item in completed.reviews] == original_text
    audit = completed.evidence_validation.audits[0]  # type: ignore[union-attr]
    assert all("语义关系" in item.reason for item in audit.judgments)


def test_evidence_api_starts_polls_and_exposes_findings(tmp_path: Path) -> None:
    reviews = [review(f"R{index:06d}", f"Offline evidence {index}") for index in range(1, 6)]
    item = candidate([review_item.id for review_item in reviews])
    provider = EvidenceMockProvider({review_item.id: EvidenceStance.SUPPORTS for review_item in reviews})
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "evidence-api.db",
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
        evidence_batch_size=3,
        evidence_high_strength_min_count=5,
    )
    app = create_app(settings=settings, semantic_provider_factory=lambda _: provider)
    app.state.run_store.save(phase3_result(reviews, item))

    with TestClient(app) as client:
        response = client.post(f"/api/analysis/{RUN_ID}/evidence", json={})
        assert response.status_code == 202
        for _ in range(100):
            run_response = client.get(f"/api/analysis/{RUN_ID}")
            payload = run_response.json()
            if payload["run"]["status"] in {"COMPLETED", "WARNING", "FAILED"}:
                break
            sleep(0.01)
        assert payload["run"]["status"] == "COMPLETED"
        assert payload["run"]["current_stage"] == "FINDING_FINALIZATION"
        assert payload["evidence_validation"]["finding_count"] == 1
        finding_payload = client.get(f"/api/analysis/{RUN_ID}/findings").json()
        assert finding_payload["findings"][0]["status"] == "SUPPORTED"
        assert len(finding_payload["audits"][0]["judgments"]) == 5


def test_candidate_scope_function_rejects_cross_run_candidate() -> None:
    with pytest.raises(EvidenceValidationError) as raised:
        validate_candidate_evidence_scope(
            candidate(["R000001"], run_id="RUN-OTHER"),
            analysis_run_id=RUN_ID,
            current_run_review_ids={"R000001"},
            cross_run_owner=lambda _: None,
        )
    assert raised.value.code == "CROSS_RUN_REFERENCE"
