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
    ArtifactValidationStatus,
    CleaningStatistics,
    EvidenceMetrics,
    EvidenceStrength,
    EvidenceValidationResult,
    Finding,
    FindingEvidenceStatus,
    FindingValidationMetadata,
    ImpactLevel,
    IngestionResult,
    PipelineStage,
    PRDSectionProposal,
    ProviderMetadata,
    RequirementDraftOutput,
    RequirementGroundingDecision,
    RequirementGroundingOutput,
    RequirementGroundingVerdict,
    RequirementPriority,
    RequirementProposal,
    Review,
    SourceType,
    StructuredPRDDraft,
    StructuredPRDDraftOutput,
    TestCase as DomainTestCase,
    TestCaseDraftOutput as DomainTestCaseDraftOutput,
    TestCaseProposal as DomainTestCaseProposal,
    TestCaseType as DomainTestCaseType,
    VersionPlanDraft,
    VersionPlanDraftOutput,
    VersionPlanItemProposal,
)
from app.services.product_planning import ProductPlanningError, ProductPlanningService
from app.services.product_rules import (
    ProductValidationError,
    calculate_traceability,
    finalize_structured_prd,
    finalize_version_plan,
    recommend_priority,
    validate_findings_for_planning,
)
from app.storage import RunStore


RUN_ID = "RUN-PRODUCT-001"
NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def review(review_id: str, *, run_id: str = RUN_ID, text: Optional[str] = None) -> Review:
    return Review(
        id=review_id,
        analysis_run_id=run_id,
        source="test_fixture",
        rating=2,
        title="Product planning fixture",
        text=text or f"User evidence for {review_id}.",
        version="5.0",
        language="en-US",
        created_at=NOW,
    )


def finding(
    finding_id: str,
    review_ids: List[str],
    *,
    status: FindingEvidenceStatus = FindingEvidenceStatus.SUPPORTED,
    run_id: str = RUN_ID,
) -> Finding:
    eligible = status == FindingEvidenceStatus.SUPPORTED
    support_count = len(review_ids) if status != FindingEvidenceStatus.UNSUPPORTED else 0
    supports = review_ids if support_count else []
    confidence = 0.9 if eligible else 0.2
    return Finding(
        id=finding_id,
        analysis_run_id=run_id,
        topic="Subscription transparency",
        title=f"Validated problem {finding_id}",
        problem=f"Users encounter a validated problem represented by {finding_id}.",
        summary=f"Current-run evidence supports the bounded claim for {finding_id}.",
        supporting_review_ids=supports,
        conflicting_review_ids=[],
        support_count=support_count,
        conflict_count=0,
        confidence=confidence,
        evidence_strength=(EvidenceStrength.HIGH if eligible else EvidenceStrength.LOW),
        status=status,
        uncertainty="The result reflects the current review sample.",
        limitations=["Uploaded fixture data is user supplied."],
        validation_metadata=FindingValidationMetadata(
            analysis_run_id=run_id,
            audit_id=f"EVA-{finding_id}",
            finding_candidate_id=f"FC-{finding_id}",
            metrics=EvidenceMetrics(
                validated_review_count=max(1, len(review_ids)),
                relevant_review_count=support_count,
                support_count=support_count,
                conflict_count=0,
                neutral_count=0,
                irrelevant_count=0 if support_count else max(1, len(review_ids)),
                support_ratio=1 if support_count else 0,
                conflict_ratio=0,
                evidence_density=1 if support_count else 0,
                average_support_relevance=0.92 if support_count else 0,
            ),
            validated_review_count=max(1, len(review_ids)),
            batch_count=1,
            eligible_for_requirement_generation=eligible,
            validation_time=NOW,
        ),
    )


def phase4_result(
    *,
    run_id: str = RUN_ID,
    output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.EN_US,
    include_blocked: bool = True,
) -> IngestionResult:
    reviews = [review(f"R{index:06d}", run_id=run_id) for index in range(1, 13)]
    findings = [
        finding("F-001", [item.id for item in reviews[:6]], run_id=run_id),
        finding("F-002", [item.id for item in reviews[6:12]], run_id=run_id),
    ]
    if include_blocked:
        findings.extend(
            [
                finding(
                    "F-WEAK",
                    [reviews[0].id, reviews[1].id],
                    status=FindingEvidenceStatus.WEAK,
                    run_id=run_id,
                ),
                finding(
                    "F-UNSUPPORTED",
                    [reviews[2].id],
                    status=FindingEvidenceStatus.UNSUPPORTED,
                    run_id=run_id,
                ),
            ]
        )
    evidence = EvidenceValidationResult(
        analysis_run_id=run_id,
        total_candidate_count=len(findings),
        validated_candidate_count=len(findings),
        validated_review_count=len(reviews),
        batch_count=len(findings),
        batch_size=20,
        model_provider="mock-runtime-llm",
        model_name="mock-evidence",
        findings=findings,
        audits=[],
        validation_time=NOW,
    )
    return IngestionResult(
        analysis_run_id=run_id,
        run=AnalysisRun(
            id=run_id,
            source_type=SourceType.JSON,
            analysis_goal="Prioritize grounded subscription and access problems.",
            output_language=output_language,
            resolved_output_language=output_language,
            status=AnalysisRunStatus.WARNING,
            current_stage=PipelineStage.FINDING_FINALIZATION,
            last_successful_stage=PipelineStage.FINDING_FINALIZATION,
            progress=100,
            warnings=["Uploaded fixture data is user supplied."],
            total_review_count=len(reviews),
            analyzed_review_count=len(reviews),
            sampling_strategy="NONE",
            batch_count=1,
            batch_size=len(reviews),
        ),
        provider=ProviderMetadata(
            analysis_run_id=run_id,
            source="json_upload",
            collection_time=NOW,
            source_limitations=["Uploaded fixture data is user supplied."],
        ),
        statistics=CleaningStatistics(
            analysis_run_id=run_id,
            raw_review_count=len(reviews),
            clean_review_count=len(reviews),
            duplicate_count=0,
            invalid_count=0,
            empty_count=0,
            retention_rate=1,
        ),
        reviews=reviews,
        evidence_validation=evidence,
    )


class ProductMockProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-product-model"

    def __init__(
        self,
        *,
        ungrounded: bool = False,
        partial_grounding: bool = False,
        invalid_test_requirement: bool = False,
        invalid_prd_finding: bool = False,
    ) -> None:
        self.ungrounded = ungrounded
        self.partial_grounding = partial_grounding
        self.invalid_test_requirement = invalid_test_requirement
        self.invalid_prd_finding = invalid_prd_finding
        self.calls: List[Dict[str, object]] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
    ) -> BaseModel:
        payload = json.loads(user_prompt)
        self.calls.append({"schema_name": schema_name, "payload": payload})
        chinese = payload.get("output_language") == "zh-CN"
        if schema_name == "RequirementDraftOutput":
            return RequirementDraftOutput(
                analysis_run_id=payload["analysis_run_id"],
                requirements=[
                    RequirementProposal(
                        title=(f"解决 {item['title']}" if chinese else f"Resolve {item['title']}"),
                        user_problem=item["problem"],
                        description=(
                            f"提供与 {item['title']} 边界一致的可执行改进。"
                            if chinese
                            else f"Deliver an actionable improvement bounded by {item['title']}."
                        ),
                        finding_ids=[item["id"]],
                        proposed_priority=RequirementPriority.P0,
                        impact=ImpactLevel.HIGH,
                        acceptance_criteria=(
                            ["用户在操作前可以识别功能状态。", "完成操作后结果状态清晰可验证。"]
                            if chinese
                            else [
                                "The user can identify the feature state before taking action.",
                                "The completed action exposes an observable final state.",
                            ]
                        ),
                    )
                    for item in payload["validated_findings"]
                ],
            )
        if schema_name == "RequirementGroundingOutput":
            decisions = []
            for index, draft in enumerate(payload["drafts"]):
                verdict = (
                    RequirementGroundingVerdict.UNGROUNDED
                    if self.ungrounded
                    else RequirementGroundingVerdict.PARTIAL
                    if self.partial_grounding
                    else RequirementGroundingVerdict.GROUNDED
                )
                decisions.append(
                    RequirementGroundingDecision(
                        analysis_run_id=payload["analysis_run_id"],
                        requirement_draft_id=draft["id"],
                        verdict=verdict,
                        reason=("需求保持在洞察边界内。" if chinese else "The Requirement stays within the Finding boundary."),
                        acceptance_criteria_testable=True,
                        revised_title=(f"Bounded {draft['title']}" if self.partial_grounding else None),
                        revised_user_problem=(draft["user_problem"] if self.partial_grounding else None),
                        revised_description=(draft["description"] if self.partial_grounding else None),
                        revised_acceptance_criteria=(draft["acceptance_criteria"] if self.partial_grounding else None),
                    )
                )
            return RequirementGroundingOutput(
                analysis_run_id=payload["analysis_run_id"], decisions=decisions
            )
        if schema_name == "VersionPlanDraftOutput":
            return VersionPlanDraftOutput(
                analysis_run_id=payload["analysis_run_id"],
                title="证据驱动版本规划" if chinese else "Evidence-grounded release plan",
                summary="优先交付已验证需求。" if chinese else "Deliver validated Requirements in priority order.",
                items=[
                    VersionPlanItemProposal(
                        version="V1.1",
                        theme="透明体验" if chinese else "Transparent experience",
                        goal="解决已验证用户问题。" if chinese else "Address validated user problems.",
                        requirement_ids=payload["allowed_requirement_ids"],
                        rationale="证据和优先级支持本版本范围。" if chinese else "Evidence and priority support this release scope.",
                        dependencies=[],
                        risk="变更必须避免影响现有流程。" if chinese else "Changes must avoid regressions in existing flows.",
                        scope_note="仅包含当前分析任务的需求。" if chinese else "Limited to current-run Requirements.",
                    )
                ],
            )
        if schema_name == "StructuredPRDDraftOutput":
            finding_ids = payload["allowed_finding_ids"]
            if self.invalid_prd_finding:
                finding_ids = ["F-UNSUPPORTED"]
            req_ids = payload["allowed_requirement_ids"]
            version_ids = payload["allowed_version_item_ids"]
            return StructuredPRDDraftOutput(
                analysis_run_id=payload["analysis_run_id"],
                title="产品改进 PRD" if chinese else "Product Improvement PRD",
                product_goal="解决已验证用户问题。" if chinese else "Resolve the validated user problems.",
                background="基于验证洞察。" if chinese else "Based on validated Findings.",
                analysis_scope="当前分析任务。" if chinese else "Current analysis run.",
                user_problems=[PRDSectionProposal(title="User problems", content="Validated problems.", finding_ids=finding_ids)],
                findings_summary=[PRDSectionProposal(title="Findings", content="Validated Findings.", finding_ids=finding_ids)],
                requirements=[PRDSectionProposal(title="Requirements", content="Validated Requirements.", requirement_ids=req_ids)],
                release_plan=[PRDSectionProposal(title="Release", content="Validated release.", requirement_ids=req_ids, version_item_ids=version_ids)],
                acceptance_criteria=[PRDSectionProposal(title="Acceptance", content="Inherited criteria.", requirement_ids=req_ids)],
                assumptions=payload["allowed_assumptions"],
                limitations=payload["known_limitations"],
                evidence_summary="Evidence references are supplied by validated artifacts.",
                version_plan_id=payload["version_plan_id"],
            )
        if schema_name == "TestCaseDraftOutput":
            requirement_ids = list(payload["allowed_requirement_ids"])
            if self.invalid_test_requirement:
                requirement_ids = ["REQ-UNKNOWN"]
            return DomainTestCaseDraftOutput(
                analysis_run_id=payload["analysis_run_id"],
                test_cases=[
                    DomainTestCaseProposal(
                        requirement_id=requirement_id,
                        title=f"Verify {requirement_id}",
                        preconditions=["A supported build is installed."],
                        steps=["Open the relevant workflow.", "Complete the requirement-specific user action."],
                        expected_result="The observable result satisfies the linked Requirement Acceptance Criteria.",
                        test_type=DomainTestCaseType.FUNCTIONAL,
                        proposed_priority=RequirementPriority.P0,
                    )
                    for requirement_id in requirement_ids
                ],
            )
        raise AssertionError(f"Unexpected schema {schema_name}")


class FailureProvider(LLMProvider):
    provider_name = "mock-runtime-llm"
    model_name = "mock-product-model"

    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.call_count = 0

    def generate_structured(self, **_: object) -> BaseModel:
        self.call_count += 1
        raise self.error


def make_service(
    tmp_path: Path,
    result: IngestionResult,
    provider: LLMProvider,
    *,
    retries: int = 1,
) -> ProductPlanningService:
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "product-tests.db",
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
        llm_max_retries=retries,
        product_p0_min_support_count=20,
        product_p1_min_support_count=8,
    )
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    store.save(result)
    return ProductPlanningService(settings, store, provider_factory=lambda _: provider)


def test_supported_findings_generate_grounded_complete_product_plan(tmp_path: Path) -> None:
    result = phase4_result()
    provider = ProductMockProvider()
    service = make_service(tmp_path, result, provider)

    completed = service.generate(RUN_ID)

    planning = completed.product_planning
    assert planning is not None
    assert completed.run.last_successful_stage is PipelineStage.TRACEABILITY_VALIDATION
    assert len(planning.requirements) == 2
    assert all("WEAK" not in requirement.finding_ids for requirement in planning.requirements)
    finding_by_id = {item.id: item for item in result.evidence_validation.findings}  # type: ignore[union-attr]
    for requirement in planning.requirements:
        inherited = {
            review_id
            for finding_id in requirement.finding_ids
            for review_id in finding_by_id[finding_id].supporting_review_ids
        }
        assert set(requirement.review_ids) == inherited
        assert requirement.validation_result is ArtifactValidationStatus.REVISED
    assert planning.version_plan is not None
    assert {item for version in planning.version_plan.items for item in version.requirement_ids} == {
        requirement.id for requirement in planning.requirements
    }
    assert planning.prd_artifact is not None
    assert planning.prd_artifact.rendered_markdown.startswith("# ")
    assert ".." not in planning.prd_artifact.structured_prd.analysis_scope
    assert len(planning.test_cases) == 2
    assert planning.traceability is not None
    assert planning.traceability.overall_traceability_coverage == 1


def test_unsupported_and_weak_findings_are_blocked_from_requirements(tmp_path: Path) -> None:
    result = phase4_result()
    service = make_service(tmp_path, result, ProductMockProvider())
    completed = service.generate(RUN_ID)
    finding_ids = {
        finding_id
        for requirement in completed.product_planning.requirements  # type: ignore[union-attr]
        for finding_id in requirement.finding_ids
    }
    assert "F-WEAK" not in finding_ids
    assert "F-UNSUPPORTED" not in finding_ids
    assert any("non-eligible Findings" in warning for warning in completed.run.warnings)


def test_weak_finding_cannot_be_recommended_p0() -> None:
    weak = finding("F-WEAK", ["R000001", "R000002"], status=FindingEvidenceStatus.WEAK)
    priority, _, _ = recommend_priority(
        [weak], ImpactLevel.HIGH, Settings(_env_file=None)
    )
    assert priority is RequirementPriority.P2


def test_requirement_priority_is_deterministically_revised(tmp_path: Path) -> None:
    completed = make_service(tmp_path, phase4_result(), ProductMockProvider()).generate(RUN_ID)
    requirement = completed.product_planning.requirements[0]  # type: ignore[union-attr]
    assert requirement.final_priority is RequirementPriority.P2
    assert requirement.generation_metadata.priority_adjusted
    assert requirement.validation_result is ArtifactValidationStatus.REVISED


def test_partial_requirement_claim_is_revised_and_original_draft_is_preserved(tmp_path: Path) -> None:
    completed = make_service(
        tmp_path, phase4_result(), ProductMockProvider(partial_grounding=True)
    ).generate(RUN_ID)
    planning = completed.product_planning
    assert planning is not None
    assert planning.requirement_drafts
    assert all(requirement.title.startswith("Bounded ") for requirement in planning.requirements)
    assert all(
        requirement.generation_metadata.grounding_verdict
        is RequirementGroundingVerdict.PARTIAL
        for requirement in planning.requirements
    )
    assert all(
        validation.disposition is ArtifactValidationStatus.REVISED
        for validation in planning.requirement_validations
    )


def test_invalid_and_cross_run_finding_evidence_are_rejected(tmp_path: Path) -> None:
    invalid = phase4_result(include_blocked=False)
    bad_finding = invalid.evidence_validation.findings[0].model_copy(  # type: ignore[union-attr]
        update={"supporting_review_ids": ["R999999"], "support_count": 1}
    )
    invalid.evidence_validation.findings[0] = bad_finding  # type: ignore[union-attr]
    provider = ProductMockProvider()
    service = make_service(tmp_path, invalid, provider)
    with pytest.raises(ProductPlanningError) as raised:
        service.generate(RUN_ID)
    assert raised.value.code == "INVALID_REVIEW_ID"
    assert provider.calls == []

    other = phase4_result(run_id="RUN-OTHER", include_blocked=False)
    other.reviews.append(review("RX-OTHER", run_id="RUN-OTHER"))
    current = phase4_result(include_blocked=False)
    current.evidence_validation.findings[0] = current.evidence_validation.findings[0].model_copy(  # type: ignore[union-attr]
        update={"supporting_review_ids": ["RX-OTHER"], "support_count": 1}
    )
    service = make_service(tmp_path / "cross", current, provider)
    service.store.save(other)
    with pytest.raises(ProductPlanningError) as cross_raised:
        service.generate(RUN_ID)
    assert cross_raised.value.code == "CROSS_RUN_REFERENCE"


def test_version_plan_rejects_omitted_requirement(tmp_path: Path) -> None:
    completed = make_service(tmp_path, phase4_result(), ProductMockProvider()).generate(RUN_ID)
    planning = completed.product_planning
    bad_draft = planning.version_plan_draft.model_copy(  # type: ignore[union-attr]
        update={"items": [planning.version_plan_draft.items[0].model_copy(update={"requirement_ids": [planning.requirements[0].id]})]}
    )
    with pytest.raises(ProductValidationError) as raised:
        finalize_version_plan(
            bad_draft,
            planning.requirements,
            provider_name="mock",
            model_name="mock",
        )
    assert raised.value.code == "INCOMPLETE_VERSION_PLAN"


def test_structured_prd_schema_and_unsupported_reference_rejection(tmp_path: Path) -> None:
    result = phase4_result()
    completed = make_service(tmp_path, result, ProductMockProvider()).generate(RUN_ID)
    planning = completed.product_planning
    assert planning.prd_artifact.structured_prd.requirements  # type: ignore[union-attr]
    bad = planning.structured_prd_draft.model_copy(  # type: ignore[union-attr]
        update={
            "user_problems": [
                PRDSectionProposal(
                    title="Unsupported",
                    content="Must not enter final PRD.",
                    finding_ids=["F-UNSUPPORTED"],
                )
            ]
        }
    )
    with pytest.raises(ProductValidationError) as raised:
        finalize_structured_prd(
            bad,
            result,
            result.evidence_validation.findings,  # type: ignore[union-attr]
            planning.requirements,
            planning.version_plan,
        )
    assert raised.value.code == "PRD_UNSUPPORTED_REFERENCE"


def test_test_case_linkage_and_evidence_inheritance(tmp_path: Path) -> None:
    completed = make_service(tmp_path, phase4_result(), ProductMockProvider()).generate(RUN_ID)
    planning = completed.product_planning
    requirement_by_id = {item.id: item for item in planning.requirements}  # type: ignore[union-attr]
    for test_case in planning.test_cases:  # type: ignore[union-attr]
        assert set(test_case.source_review_ids) == set(
            requirement_by_id[test_case.requirement_id].review_ids
        )
        assert len(test_case.steps) >= 2


def test_test_case_with_unknown_requirement_is_rejected_without_fake_tests(tmp_path: Path) -> None:
    service = make_service(
        tmp_path, phase4_result(), ProductMockProvider(invalid_test_requirement=True)
    )
    with pytest.raises(ProductPlanningError) as raised:
        service.generate(RUN_ID)
    assert raised.value.code == "INVALID_REQUIREMENT_ID"
    persisted = service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.product_planning is not None
    assert persisted.product_planning.requirements
    assert persisted.product_planning.prd_artifact is not None
    assert persisted.product_planning.test_cases == []


def test_invalid_test_case_evidence_is_a_traceability_hard_failure(tmp_path: Path) -> None:
    completed = make_service(tmp_path, phase4_result(), ProductMockProvider()).generate(RUN_ID)
    planning = completed.product_planning
    test_case = planning.test_cases[0]  # type: ignore[union-attr]
    invalid = DomainTestCase.model_validate(
        {**test_case.model_dump(), "source_review_ids": ["R999999"]}
    )
    coverage = calculate_traceability(
        completed,
        completed.evidence_validation.findings[:2],  # type: ignore[union-attr]
        planning.requirements,
        [invalid, *planning.test_cases[1:]],
    )
    assert coverage.hard_failures
    assert coverage.test_case_traceability_coverage < 1


def test_output_language_propagates_to_every_product_prompt(tmp_path: Path) -> None:
    provider = ProductMockProvider()
    completed = make_service(
        tmp_path,
        phase4_result(output_language=AnalysisOutputLanguage.ZH_CN),
        provider,
    ).generate(RUN_ID)
    assert completed.product_planning.requirements[0].title.startswith("解决")  # type: ignore[union-attr]
    assert "。。" not in completed.product_planning.prd_artifact.structured_prd.analysis_scope  # type: ignore[union-attr]
    assert all(call["payload"].get("output_language") == "zh-CN" for call in provider.calls)


def test_ungrounded_requirement_is_rejected_and_audited(tmp_path: Path) -> None:
    service = make_service(tmp_path, phase4_result(), ProductMockProvider(ungrounded=True))
    with pytest.raises(ProductPlanningError) as raised:
        service.generate(RUN_ID)
    assert raised.value.code == "NO_VALID_REQUIREMENTS"
    persisted = service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status is AnalysisRunStatus.FAILED
    assert persisted.product_planning is not None
    assert persisted.product_planning.requirement_drafts
    assert all(
        validation.disposition is ArtifactValidationStatus.REJECTED
        for validation in persisted.product_planning.requirement_validations
    )
    assert persisted.product_planning.requirements == []


@pytest.mark.parametrize(
    "error",
    [
        LLMProviderError("LLM_TIMEOUT", "Timed out."),
        LLMProviderError("LLM_INVALID_JSON", "Malformed structured output."),
        LLMProviderError("LLM_PROVIDER_ERROR", "Provider unavailable."),
    ],
)
def test_provider_failure_preserves_validated_findings_without_fake_artifacts(
    tmp_path: Path, error: LLMProviderError
) -> None:
    provider = FailureProvider(error)
    service = make_service(tmp_path, phase4_result(), provider, retries=1)
    with pytest.raises(ProductPlanningError):
        service.generate(RUN_ID)
    persisted = service.store.get(RUN_ID)
    assert persisted is not None
    assert persisted.run.status is AnalysisRunStatus.FAILED
    assert persisted.evidence_validation is not None
    assert persisted.evidence_validation.findings
    assert persisted.product_planning is not None
    assert persisted.product_planning.requirements == []
    assert persisted.product_planning.prd_artifact is None
    assert persisted.product_planning.test_cases == []
    assert provider.call_count == 2


def test_product_plan_api_starts_polls_and_returns_artifacts(tmp_path: Path) -> None:
    provider = ProductMockProvider()
    settings = Settings(
        _env_file=None,
        sqlite_database_path=tmp_path / "product-api.db",
        llm_provider=provider.provider_name,
        llm_model=provider.model_name,
    )
    app = create_app(settings=settings, semantic_provider_factory=lambda _: provider)
    app.state.run_store.save(phase4_result())
    with TestClient(app) as client:
        response = client.post(f"/api/analysis/{RUN_ID}/product-plan", json={})
        assert response.status_code == 202
        for _ in range(100):
            payload = client.get(f"/api/analysis/{RUN_ID}").json()
            if payload["run"]["status"] in {"COMPLETED", "WARNING", "FAILED"}:
                break
            sleep(0.01)
        assert payload["run"]["last_successful_stage"] == "TRACEABILITY_VALIDATION"
        view = client.get(f"/api/analysis/{RUN_ID}/product-plan")
        assert view.status_code == 200
        planning = view.json()["product_planning"]
        assert len(planning["requirements"]) == 2
        assert planning["prd_artifact"]["rendered_markdown"].startswith("# ")
        prd = client.get(f"/api/analysis/{RUN_ID}/product-plan/prd.md")
        assert prd.status_code == 200
        assert prd.headers["content-disposition"] == 'attachment; filename="PRD.md"'
        assert prd.text.startswith("# ")


def test_structured_output_enums_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        RequirementProposal(
            title="Invalid",
            user_problem="Invalid",
            description="Invalid",
            finding_ids=["F-001"],
            proposed_priority="URGENT",
            impact="HIGH",
            acceptance_criteria=["Observable criterion one.", "Observable criterion two."],
        )
