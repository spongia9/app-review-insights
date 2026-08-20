from pathlib import Path

from app.models import (
    AnalysisRunStatus,
    ArtifactValidationStatus,
    FindingEvidenceStatus,
    Requirement,
    TestCase as DomainTestCase,
)
from app.services.traceability import FinalTraceabilityValidator
from tests.test_product_planning import (
    ProductMockProvider,
    make_service,
    phase4_result,
)


def completed_plan(tmp_path: Path):
    return make_service(tmp_path, phase4_result(), ProductMockProvider()).generate(
        "RUN-PRODUCT-001"
    )


def test_forward_reverse_and_coverage_are_structured(tmp_path: Path) -> None:
    completed = completed_plan(tmp_path)
    trace = FinalTraceabilityValidator().validate(completed)

    assert trace.coverage.hard_failures == []
    assert trace.coverage.finding_evidence_coverage == 0.75
    assert trace.coverage.requirement_traceability_coverage == 1
    assert trace.coverage.test_case_traceability_coverage == 1
    assert trace.coverage.overall_traceability_coverage == 0.875
    forward = next(item for item in trace.forward if item.review_id == "R000001")
    assert "F-001" in forward.finding_ids
    assert forward.requirement_ids
    assert forward.test_case_ids
    reverse = trace.reverse[0]
    requirement = next(
        item
        for item in completed.product_planning.requirements
        if item.id == reverse.requirement_id
    )
    assert reverse.finding_ids == requirement.finding_ids
    assert set(reverse.review_ids) == set(requirement.review_ids)
    assert trace.matrix
    assert all(row.analysis_run_id == completed.analysis_run_id for row in trace.matrix)


def test_invalid_review_and_testcase_evidence_are_hard_failures(tmp_path: Path) -> None:
    completed = completed_plan(tmp_path)
    finding = completed.evidence_validation.findings[0]
    completed.evidence_validation.findings[0] = finding.model_copy(
        update={"supporting_review_ids": ["R999999"], "support_count": 1}
    )
    test_case = completed.product_planning.test_cases[0]
    completed.product_planning.test_cases[0] = test_case.model_copy(
        update={"source_review_ids": ["R999999"]}
    )

    trace = FinalTraceabilityValidator().validate(completed)

    assert any("INVALID_REVIEW_ID" in item for item in trace.coverage.hard_failures)
    assert any("BROKEN_TESTCASE_INHERITANCE" in item for item in trace.coverage.hard_failures)
    assert trace.coverage.finding_evidence_coverage < 1
    assert trace.coverage.test_case_traceability_coverage < 1


def test_invalid_finding_and_cross_run_reference_are_distinguished(tmp_path: Path) -> None:
    completed = completed_plan(tmp_path)
    requirement = completed.product_planning.requirements[0]
    completed.product_planning.requirements[0] = requirement.model_copy(
        update={"finding_ids": ["F-OTHER-RUN"]}
    )
    validator = FinalTraceabilityValidator(
        artifact_owner=lambda kind, identifier: (
            "RUN-OTHER" if kind == "Finding" and identifier == "F-OTHER-RUN" else None
        )
    )

    trace = validator.validate(completed)

    assert any("CROSS_RUN_REFERENCE" in item for item in trace.coverage.hard_failures)
    completed.product_planning.requirements[0] = requirement.model_copy(
        update={"finding_ids": ["F-MISSING"]}
    )
    trace = FinalTraceabilityValidator().validate(completed)
    assert any("INVALID_FINDING_ID" in item for item in trace.coverage.hard_failures)


def test_rejected_requirement_in_prd_is_a_hard_failure(tmp_path: Path) -> None:
    completed = completed_plan(tmp_path)
    source = completed.product_planning.requirements[0]
    rejected = Requirement.model_validate(
        {
            **source.model_dump(),
            "id": "REQ-REJECTED",
            "validation_result": ArtifactValidationStatus.REJECTED,
        }
    )
    planning = completed.product_planning
    planning.requirements.append(rejected)
    structured = planning.prd_artifact.structured_prd
    section = structured.requirements[0]
    structured.requirements[0] = section.model_copy(
        update={"requirement_ids": ["REQ-REJECTED"]}
    )

    trace = FinalTraceabilityValidator().validate(completed)

    assert any(
        "REJECTED_REQUIREMENT_REFERENCE" in item
        for item in trace.coverage.hard_failures
    )


def test_assumption_revision_rejection_and_finding_warnings_are_counted(
    tmp_path: Path,
) -> None:
    completed = completed_plan(tmp_path)
    source = completed.product_planning.requirements[0]
    assumption = Requirement.model_validate(
        {
            **source.model_dump(),
            "id": "REQ-ASSUMPTION",
            "assumption": True,
            "validation_result": ArtifactValidationStatus.ASSUMPTION,
        }
    )
    completed.product_planning.requirements.append(assumption)
    completed.product_planning.requirement_validations.append(
        completed.product_planning.requirement_validations[0].model_copy(
            update={
                "id": "VAL-REJECTED",
                "target_id": "REQ-DRAFT-REJECTED",
                "disposition": ArtifactValidationStatus.REJECTED,
            }
        )
    )

    trace = FinalTraceabilityValidator().validate(completed)

    assert trace.assumption_count == 1
    assert trace.revised_count >= 1
    assert trace.rejected_count == 1
    assert trace.weak_count == 1
    assert trace.unsupported_count == 1
    assert any("explicit assumption" in item for item in trace.coverage.warnings)


def test_validation_failed_status_is_a_stable_domain_value() -> None:
    assert AnalysisRunStatus.COMPLETED_WITH_WARNINGS.value == "COMPLETED_WITH_WARNINGS"
    assert AnalysisRunStatus.VALIDATION_FAILED.value == "VALIDATION_FAILED"


def test_testcase_reverse_traceability_preserves_requirement_chain(tmp_path: Path) -> None:
    completed = completed_plan(tmp_path)
    test_case: DomainTestCase = completed.product_planning.test_cases[0]
    trace = FinalTraceabilityValidator().validate(completed)
    reverse = next(item for item in trace.reverse if item.test_case_id == test_case.id)
    assert reverse.requirement_id == test_case.requirement_id
    assert reverse.finding_ids
    assert reverse.review_ids == test_case.source_review_ids
    assert all(
        finding.status != FindingEvidenceStatus.UNSUPPORTED
        for finding in completed.evidence_validation.findings
        if finding.id in reverse.finding_ids
    )
