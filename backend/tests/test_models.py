from datetime import datetime, timezone
from typing import Any, Dict, Type

import pytest
from pydantic import BaseModel, ValidationError

from app.models import (
    AnalysisRun,
    ArtifactValidationStatus,
    Finding,
    PRDSection,
    Requirement,
    Review,
    StructuredPRD,
    TestCase as DomainTestCase,
    ValidationResult,
    VersionPlan,
    VersionPlanItem,
)


RUN_ID = "RUN-001"


def review_payload() -> Dict[str, Any]:
    return {
        "id": "R-001",
        "analysis_run_id": RUN_ID,
        "source": "fixture",
        "source_review_id": "source-001",
        "app_id": "123456",
        "author": "Reviewer",
        "rating": 4,
        "title": "Useful update",
        "text": "The latest update is easier to use.",
        "version": "2.1.0",
        "language": "en",
        "created_at": datetime(2026, 8, 13, tzinfo=timezone.utc),
        "storefront": "us",
        "raw_data": {"source": "test"},
    }


def finding_payload() -> Dict[str, Any]:
    return {
        "id": "F-001",
        "analysis_run_id": RUN_ID,
        "topic": "Navigation clarity",
        "title": "Navigation is easier after the update",
        "problem": "Some users previously struggled to find core actions.",
        "summary": "Current evidence reports improved navigation clarity.",
        "supporting_review_ids": ["R-001"],
        "conflicting_review_ids": [],
        "support_count": 1,
        "conflict_count": 0,
        "confidence": 0.72,
        "evidence_strength": "LOW",
        "status": "WEAK",
        "uncertainty": "The sample is small.",
        "limitations": ["Single supporting review"],
        "validation_metadata": {
            "analysis_run_id": RUN_ID,
            "audit_id": "EVA-001",
            "finding_candidate_id": "FC-001",
            "metrics": {
                "validated_review_count": 1,
                "relevant_review_count": 1,
                "support_count": 1,
                "conflict_count": 0,
                "neutral_count": 0,
                "irrelevant_count": 0,
                "support_ratio": 1,
                "conflict_ratio": 0,
                "evidence_density": 1,
                "average_support_relevance": 0.9,
            },
            "validated_review_count": 1,
            "batch_count": 1,
            "eligible_for_requirement_generation": False,
            "validation_time": datetime(2026, 8, 14, tzinfo=timezone.utc),
        },
    }


def requirement_payload() -> Dict[str, Any]:
    return {
        "id": "REQ-001",
        "analysis_run_id": RUN_ID,
        "title": "Preserve navigation clarity",
        "user_problem": "Users need to find primary actions quickly.",
        "description": "Keep primary actions consistently discoverable.",
        "finding_ids": ["F-001"],
        "review_ids": ["R-001"],
        "priority": "P1",
        "recommended_priority": "P1",
        "final_priority": "P1",
        "priority_reason": "Evidence and impact justify P1.",
        "impact": "MEDIUM",
        "confidence": 0.72,
        "acceptance_criteria": ["Primary actions are visible from the main screen."],
        "target_version": "2.2.0",
        "assumption": False,
        "validation_result": "ACCEPTED",
        "generated_by": "runtime_llm",
        "generation_metadata": {
            "analysis_run_id": RUN_ID,
            "draft_id": "REQD-001",
            "validation_id": "VAL-REQ-001",
            "grounding_verdict": "GROUNDED",
            "generated_by": "runtime_llm",
            "model_provider": "mock",
            "model_name": "mock-model",
            "generated_at": datetime(2026, 8, 14, tzinfo=timezone.utc),
            "priority_adjusted": False,
        },
    }


def make_test_case_payload() -> Dict[str, Any]:
    return {
        "id": "TC-001",
        "analysis_run_id": RUN_ID,
        "requirement_id": "REQ-001",
        "source_review_ids": ["R-001"],
        "title": "Locate the primary action",
        "preconditions": ["The app is freshly launched."],
        "steps": ["Open the main screen.", "Locate the primary action."],
        "expected_result": "The primary action is visible without additional navigation.",
        "test_type": "FUNCTIONAL",
        "priority": "P1",
        "validation_result": "ACCEPTED",
        "generated_by": "runtime_llm",
        "model_provider": "mock",
        "model_name": "mock-model",
        "generated_at": datetime(2026, 8, 14, tzinfo=timezone.utc),
        "draft_id": "TCD-001",
    }


def version_plan_item_payload() -> Dict[str, Any]:
    return {
        "id": "VPI-001",
        "analysis_run_id": RUN_ID,
        "version": "2.2.0",
        "theme": "Navigation clarity",
        "goal": "Preserve discoverability of core actions.",
        "requirement_ids": ["REQ-001"],
        "rationale": "The Requirement has validated user impact.",
        "dependencies": [],
        "risk": "Navigation regressions may affect existing flows.",
        "scope_note": "Limited to primary-action discoverability.",
        "validation_result": "ACCEPTED",
    }


def prd_section_payload() -> Dict[str, Any]:
    return {
        "id": "PRDS-001",
        "analysis_run_id": RUN_ID,
        "section_type": "user_problem",
        "title": "User problem",
        "content": "Users need to find primary actions quickly.",
        "finding_ids": ["F-001"],
        "requirement_ids": ["REQ-001"],
        "assumption": False,
        "validation_result": "ACCEPTED",
    }


def test_review_model_validation() -> None:
    review = Review.model_validate(review_payload())

    assert review.analysis_run_id == RUN_ID
    assert review.rating == 4
    assert review.storefront == "us"


def test_review_rejects_rating_outside_app_store_range() -> None:
    payload = review_payload()
    payload["rating"] = 6

    with pytest.raises(ValidationError):
        Review.model_validate(payload)


def test_finding_model_validation() -> None:
    finding = Finding.model_validate(finding_payload())

    assert finding.status.value == "WEAK"
    assert finding.supporting_review_ids == ["R-001"]


def test_finding_rejects_invalid_status() -> None:
    payload = finding_payload()
    payload["status"] = "VALIDATED"

    with pytest.raises(ValidationError):
        Finding.model_validate(payload)


def test_requirement_model_validation() -> None:
    requirement = Requirement.model_validate(requirement_payload())

    assert requirement.validation_result is ArtifactValidationStatus.ACCEPTED
    assert requirement.analysis_run_id == RUN_ID


def test_test_case_model_validation() -> None:
    test_case = DomainTestCase.model_validate(make_test_case_payload())

    assert test_case.requirement_id == "REQ-001"
    assert test_case.source_review_ids == ["R-001"]


def test_generated_artifact_rejects_invalid_validation_result() -> None:
    payload = requirement_payload()
    payload["validation_result"] = "APPROVED"

    with pytest.raises(ValidationError):
        Requirement.model_validate(payload)


def test_analysis_run_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AnalysisRun(
            id=RUN_ID,
            source_type="csv",
            status="DONE",
        )


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (Review, review_payload()),
        (Finding, finding_payload()),
        (Requirement, requirement_payload()),
        (DomainTestCase, make_test_case_payload()),
        (
            VersionPlan,
            {
                "id": "VP-001",
                "analysis_run_id": RUN_ID,
                "title": "Release plan",
                "items": [version_plan_item_payload()],
                "validation_result": "ACCEPTED",
            },
        ),
        (
            StructuredPRD,
            {
                "id": "PRD-001",
                "analysis_run_id": RUN_ID,
                "title": "Navigation PRD",
                "product_goal": "Keep core actions discoverable.",
                "sections": [prd_section_payload()],
                "version_plan_id": "VP-001",
                "validation_result": "ACCEPTED",
            },
        ),
        (
            ValidationResult,
            {
                "id": "VAL-001",
                "analysis_run_id": RUN_ID,
                "target_type": "Requirement",
                "target_id": "REQ-001",
                "disposition": "ACCEPTED",
            },
        ),
    ],
)
def test_run_scoped_models_require_analysis_run_id(
    model: Type[BaseModel], payload: Dict[str, Any]
) -> None:
    payload.pop("analysis_run_id")

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_additional_domain_models_validate() -> None:
    version_item = VersionPlanItem.model_validate(version_plan_item_payload())
    version_plan = VersionPlan(
        id="VP-001",
        analysis_run_id=RUN_ID,
        title="Release plan",
        summary="One focused release.",
        items=[version_item],
        validation_result="ACCEPTED",
        generated_by="runtime_llm",
        model_provider="mock",
        model_name="mock-model",
        generated_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    prd_section = PRDSection.model_validate(prd_section_payload())
    prd = StructuredPRD(
        id="PRD-001",
        analysis_run_id=RUN_ID,
        title="Navigation PRD",
        product_goal="Keep core actions discoverable.",
        background="The plan uses validated review evidence.",
        analysis_scope="Current analysis run only.",
        user_problems=[prd_section],
        findings_summary=[prd_section.model_copy(update={"id": "PRDS-002"})],
        requirements=[prd_section.model_copy(update={"id": "PRDS-003"})],
        release_plan=[prd_section.model_copy(update={"id": "PRDS-004"})],
        acceptance_criteria=[prd_section.model_copy(update={"id": "PRDS-005"})],
        assumptions=[],
        limitations=[],
        evidence_summary=prd_section.model_copy(update={"id": "PRDS-006"}),
        version_plan_id=version_plan.id,
        validation_result="ACCEPTED",
    )
    validation = ValidationResult(
        id="VAL-001",
        analysis_run_id=RUN_ID,
        target_type="StructuredPRD",
        target_id=prd.id,
        disposition="ACCEPTED",
    )

    assert version_plan.items[0].analysis_run_id == RUN_ID
    assert prd.user_problems[0].finding_ids == ["F-001"]
    assert validation.disposition is ArtifactValidationStatus.ACCEPTED
