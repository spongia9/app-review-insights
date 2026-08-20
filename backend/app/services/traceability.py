from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.models import (
    ArtifactValidationStatus,
    EvidenceRole,
    FinalTraceabilityResult,
    Finding,
    FindingEvidenceStatus,
    ForwardTraceability,
    IngestionResult,
    Requirement,
    ReverseTraceability,
    TestCase,
    TraceabilityCoverage,
    TraceabilityMatrixRow,
    ValidationResult,
)


ArtifactOwner = Callable[[str, str], Optional[str]]


def _stable(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _coverage(valid_count: int, denominator: int) -> Optional[float]:
    return round(valid_count / denominator, 4) if denominator else None


def final_traceability_summary(result: FinalTraceabilityResult):
    from app.models import FinalTraceabilitySummary

    return FinalTraceabilitySummary(
        analysis_run_id=result.analysis_run_id,
        matrix_row_count=len(result.matrix),
        overall_traceability_coverage=result.coverage.overall_traceability_coverage,
        hard_failure_count=len(result.coverage.hard_failures),
        warning_count=len(result.coverage.warnings),
        unsupported_count=result.unsupported_count,
        assumption_count=result.assumption_count,
        revised_count=result.revised_count,
        rejected_count=result.rejected_count,
        validated_at=result.validated_at,
    )


class FinalTraceabilityValidator:
    """Deterministically validates the complete current-run artifact graph."""

    def __init__(self, artifact_owner: Optional[ArtifactOwner] = None) -> None:
        self.artifact_owner = artifact_owner or (lambda _kind, _identifier: None)

    def validate(self, result: IngestionResult) -> FinalTraceabilityResult:
        run_id = result.analysis_run_id
        validated_at = datetime.now(timezone.utc)
        hard_failures: List[str] = []
        warnings: List[str] = list(result.run.warnings)
        validations: List[ValidationResult] = []
        reviews = {review.id: review for review in result.reviews}
        findings = list(result.evidence_validation.findings) if result.evidence_validation else []
        planning = result.product_planning
        requirements = list(planning.requirements) if planning else []
        tests = list(planning.test_cases) if planning else []
        version_plan = planning.version_plan if planning else None
        prd_artifact = planning.prd_artifact if planning else None
        finding_by_id = {item.id: item for item in findings}
        requirement_by_id = {item.id: item for item in requirements}

        if result.evidence_validation is None:
            hard_failures.append("MISSING_FINDINGS: final traceability requires validated Findings.")
        if planning is None:
            hard_failures.append("MISSING_PRODUCT_PLAN: final traceability requires product-planning artifacts.")

        finding_valid_count = 0
        for index, finding in enumerate(findings, start=1):
            errors: List[str] = []
            item_warnings: List[str] = []
            if finding.analysis_run_id != run_id:
                errors.append(f"CROSS_RUN_REFERENCE: Finding {finding.id} belongs to another run.")
            if finding.support_count != len(finding.supporting_review_ids):
                errors.append(f"COUNT_MISMATCH: Finding {finding.id} support_count is invalid.")
            if finding.conflict_count != len(finding.conflicting_review_ids):
                errors.append(f"COUNT_MISMATCH: Finding {finding.id} conflict_count is invalid.")
            if len(finding.supporting_review_ids) != len(set(finding.supporting_review_ids)):
                errors.append(f"DUPLICATE_REFERENCE: Finding {finding.id} repeats supporting Reviews.")
            if len(finding.conflicting_review_ids) != len(set(finding.conflicting_review_ids)):
                errors.append(f"DUPLICATE_REFERENCE: Finding {finding.id} repeats conflicting Reviews.")
            if set(finding.supporting_review_ids) & set(finding.conflicting_review_ids):
                errors.append(f"OVERLAPPING_EVIDENCE: Finding {finding.id} has overlapping evidence.")
            for review_id in [*finding.supporting_review_ids, *finding.conflicting_review_ids]:
                self._validate_reference(
                    "Review", review_id, reviews, run_id, f"Finding {finding.id}", errors
                )
            if finding.status in {
                FindingEvidenceStatus.WEAK,
                FindingEvidenceStatus.CONFLICTED,
                FindingEvidenceStatus.INSUFFICIENT,
                FindingEvidenceStatus.UNSUPPORTED,
            }:
                item_warnings.append(
                    f"Finding {finding.id} is explicitly labeled {finding.status.value}."
                )
            has_valid_support = bool(finding.supporting_review_ids) and not errors
            finding_valid_count += int(has_valid_support)
            if not has_valid_support and finding.status != FindingEvidenceStatus.UNSUPPORTED:
                errors.append(f"MISSING_SUPPORT: Finding {finding.id} has no valid supporting Review.")
            hard_failures.extend(errors)
            warnings.extend(item_warnings)
            validations.append(
                self._validation(
                    run_id,
                    f"VAL-TRACE-F-{index:04d}",
                    "Finding",
                    finding.id,
                    errors,
                    item_warnings,
                )
            )

        applicable_requirements = [
            item
            for item in requirements
            if not item.assumption and item.validation_result != ArtifactValidationStatus.REJECTED
        ]
        traceable_requirement_count = 0
        for index, requirement in enumerate(requirements, start=1):
            errors = []
            item_warnings = []
            if requirement.analysis_run_id != run_id:
                errors.append(
                    f"CROSS_RUN_REFERENCE: Requirement {requirement.id} belongs to another run."
                )
            if requirement.validation_result == ArtifactValidationStatus.REJECTED:
                errors.append(
                    f"REJECTED_FINAL_ARTIFACT: Requirement {requirement.id} appears in final Requirements."
                )
            referenced_findings: List[Finding] = []
            for finding_id in requirement.finding_ids:
                finding = self._validate_reference(
                    "Finding",
                    finding_id,
                    finding_by_id,
                    run_id,
                    f"Requirement {requirement.id}",
                    errors,
                )
                if finding is not None:
                    referenced_findings.append(finding)
                    if (
                        finding.status == FindingEvidenceStatus.UNSUPPORTED
                        and not requirement.assumption
                    ):
                        errors.append(
                            f"UNSUPPORTED_FINDING: Requirement {requirement.id} cites {finding.id}."
                        )
            inherited = _stable(
                review_id
                for finding in referenced_findings
                for review_id in finding.supporting_review_ids
            )
            if not requirement.assumption and set(requirement.review_ids) != set(inherited):
                errors.append(
                    f"BROKEN_REQUIREMENT_INHERITANCE: Requirement {requirement.id} evidence does not equal its Findings."
                )
            for review_id in requirement.review_ids:
                self._validate_reference(
                    "Review", review_id, reviews, run_id, f"Requirement {requirement.id}", errors
                )
            if requirement.assumption or requirement.validation_result == ArtifactValidationStatus.ASSUMPTION:
                item_warnings.append(f"Requirement {requirement.id} is an explicit assumption.")
            if requirement.validation_result == ArtifactValidationStatus.REVISED:
                item_warnings.append(f"Requirement {requirement.id} was revised before acceptance.")
            if requirement in applicable_requirements and not errors:
                traceable_requirement_count += 1
            hard_failures.extend(errors)
            warnings.extend(item_warnings)
            validations.append(
                self._validation(
                    run_id,
                    f"VAL-TRACE-REQ-{index:04d}",
                    "Requirement",
                    requirement.id,
                    errors,
                    item_warnings,
                )
            )

        if version_plan is None:
            if applicable_requirements:
                hard_failures.append("MISSING_VERSION_PLAN: Requirements are not assigned to a VersionPlan.")
        else:
            version_errors: List[str] = []
            if version_plan.analysis_run_id != run_id:
                version_errors.append("CROSS_RUN_REFERENCE: VersionPlan belongs to another run.")
            assigned: List[str] = []
            for item in version_plan.items:
                if item.analysis_run_id != run_id:
                    version_errors.append(
                        f"CROSS_RUN_REFERENCE: VersionPlan item {item.id} belongs to another run."
                    )
                for requirement_id in item.requirement_ids:
                    requirement = self._validate_reference(
                        "Requirement",
                        requirement_id,
                        requirement_by_id,
                        run_id,
                        f"VersionPlan item {item.id}",
                        version_errors,
                    )
                    if requirement and requirement.validation_result == ArtifactValidationStatus.REJECTED:
                        version_errors.append(
                            f"REJECTED_REQUIREMENT_REFERENCE: VersionPlan item {item.id} cites {requirement_id}."
                        )
                assigned.extend(item.requirement_ids)
            expected = {item.id for item in applicable_requirements}
            if len(assigned) != len(set(assigned)):
                version_errors.append("DUPLICATE_VERSION_ASSIGNMENT: a Requirement appears in multiple versions.")
            if set(assigned) != expected:
                version_errors.append(
                    "INCOMPLETE_VERSION_PLAN: accepted non-assumption Requirements must be assigned exactly once."
                )
            hard_failures.extend(version_errors)
            validations.append(
                self._validation(
                    run_id,
                    "VAL-TRACE-VP-0001",
                    "VersionPlan",
                    version_plan.id,
                    version_errors,
                    [],
                )
            )

        self._validate_prd(
            run_id,
            prd_artifact,
            finding_by_id,
            requirement_by_id,
            version_plan,
            hard_failures,
            warnings,
            validations,
        )

        traceable_test_count = 0
        applicable_tests = [
            item for item in tests if item.validation_result != ArtifactValidationStatus.REJECTED
        ]
        for index, test_case in enumerate(tests, start=1):
            errors = []
            item_warnings = []
            if test_case.analysis_run_id != run_id:
                errors.append(f"CROSS_RUN_REFERENCE: TestCase {test_case.id} belongs to another run.")
            requirement = self._validate_reference(
                "Requirement",
                test_case.requirement_id,
                requirement_by_id,
                run_id,
                f"TestCase {test_case.id}",
                errors,
            )
            if test_case.validation_result == ArtifactValidationStatus.REJECTED:
                errors.append(
                    f"REJECTED_FINAL_ARTIFACT: TestCase {test_case.id} appears in final TestCases."
                )
            if requirement is not None:
                if set(test_case.source_review_ids) != set(requirement.review_ids):
                    errors.append(
                        f"BROKEN_TESTCASE_INHERITANCE: TestCase {test_case.id} evidence does not equal its Requirement."
                    )
            for review_id in test_case.source_review_ids:
                self._validate_reference(
                    "Review", review_id, reviews, run_id, f"TestCase {test_case.id}", errors
                )
            if test_case.validation_result == ArtifactValidationStatus.REVISED:
                item_warnings.append(f"TestCase {test_case.id} was revised before acceptance.")
            if test_case in applicable_tests and not errors:
                traceable_test_count += 1
            hard_failures.extend(errors)
            warnings.extend(item_warnings)
            validations.append(
                self._validation(
                    run_id,
                    f"VAL-TRACE-TC-{index:04d}",
                    "TestCase",
                    test_case.id,
                    errors,
                    item_warnings,
                )
            )

        tested_requirements = {item.requirement_id for item in applicable_tests}
        for requirement in applicable_requirements:
            if requirement.id not in tested_requirements:
                warnings.append(f"Requirement {requirement.id} has no TestCase coverage.")
        if result.evidence_validation and (
            result.evidence_validation.validated_candidate_count
            < result.evidence_validation.total_candidate_count
        ):
            warnings.append("Evidence validation covers only part of the Finding Candidate set.")
        if result.run.analyzed_review_count < len(result.reviews):
            warnings.append("Semantic analysis covers only part of the cleaned Review set.")

        finding_denominator = len(findings)
        requirement_denominator = len(applicable_requirements)
        test_denominator = len(applicable_tests)
        numerator = finding_valid_count + traceable_requirement_count + traceable_test_count
        denominator = finding_denominator + requirement_denominator + test_denominator
        coverage = TraceabilityCoverage(
            analysis_run_id=run_id,
            finding_evidence_coverage=_coverage(finding_valid_count, finding_denominator),
            requirement_traceability_coverage=_coverage(
                traceable_requirement_count, requirement_denominator
            ),
            test_case_traceability_coverage=_coverage(traceable_test_count, test_denominator),
            overall_traceability_coverage=_coverage(numerator, denominator),
            finding_denominator=finding_denominator,
            requirement_denominator=requirement_denominator,
            test_case_denominator=test_denominator,
            hard_failures=_stable(hard_failures),
            warnings=_stable(warnings),
            validated_at=validated_at,
        )
        matrix = self._build_matrix(
            run_id, findings, requirements, tests, version_plan
        )
        forward = self._build_forward(run_id, reviews, matrix)
        reverse = self._build_reverse(run_id, requirements, tests)
        dispositions = self._artifact_dispositions(result)
        assumption_count = sum(item.assumption for item in requirements)
        if prd_artifact:
            sections = self._prd_sections(prd_artifact.structured_prd)
            assumption_count += sum(section.assumption for section in sections)
        return FinalTraceabilityResult(
            id="TRACE-0001",
            analysis_run_id=run_id,
            matrix=matrix,
            forward=forward,
            reverse=reverse,
            coverage=coverage,
            validation_results=validations,
            unsupported_count=sum(
                item.status == FindingEvidenceStatus.UNSUPPORTED for item in findings
            ),
            weak_count=sum(item.status == FindingEvidenceStatus.WEAK for item in findings),
            conflicted_count=sum(
                item.status == FindingEvidenceStatus.CONFLICTED for item in findings
            ),
            assumption_count=assumption_count,
            revised_count=sum(value == ArtifactValidationStatus.REVISED for value in dispositions),
            rejected_count=sum(value == ArtifactValidationStatus.REJECTED for value in dispositions),
            validated_at=validated_at,
        )

    def _validate_reference(
        self,
        kind: str,
        identifier: str,
        current: Dict[str, object],
        run_id: str,
        source: str,
        errors: List[str],
    ):
        target = current.get(identifier)
        if target is not None:
            target_run = getattr(target, "analysis_run_id", run_id)
            if target_run != run_id:
                errors.append(
                    f"CROSS_RUN_REFERENCE: {source} cites {kind} {identifier} from another run."
                )
                return None
            return target
        owner = self.artifact_owner(kind, identifier)
        code = "CROSS_RUN_REFERENCE" if owner and owner != run_id else f"INVALID_{kind.upper()}_ID"
        errors.append(f"{code}: {source} cites unavailable {kind} {identifier}.")
        return None

    @staticmethod
    def _validation(
        run_id: str,
        validation_id: str,
        target_type: str,
        target_id: str,
        errors: Sequence[str],
        warnings: Sequence[str],
    ) -> ValidationResult:
        return ValidationResult(
            id=validation_id,
            analysis_run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            disposition=(
                ArtifactValidationStatus.REJECTED
                if errors
                else ArtifactValidationStatus.REVISED
                if warnings
                else ArtifactValidationStatus.ACCEPTED
            ),
            errors=list(errors),
            warnings=list(warnings),
        )

    def _validate_prd(
        self,
        run_id: str,
        artifact,
        findings: Dict[str, Finding],
        requirements: Dict[str, Requirement],
        version_plan,
        hard_failures: List[str],
        warnings: List[str],
        validations: List[ValidationResult],
    ) -> None:
        errors: List[str] = []
        item_warnings: List[str] = []
        if artifact is None:
            if requirements:
                errors.append("MISSING_PRD: final product output has no validated PRD artifact.")
            target_id = "PRD-NOT-AVAILABLE"
        else:
            target_id = artifact.id
            structured = artifact.structured_prd
            if artifact.analysis_run_id != run_id or structured.analysis_run_id != run_id:
                errors.append("CROSS_RUN_REFERENCE: PRD belongs to another run.")
            if version_plan is None or structured.version_plan_id != version_plan.id:
                errors.append("INVALID_VERSION_ID: PRD references an unavailable VersionPlan.")
            for section in self._prd_sections(structured):
                if section.analysis_run_id != run_id:
                    errors.append(f"CROSS_RUN_REFERENCE: PRD section {section.id} belongs to another run.")
                for finding_id in section.finding_ids:
                    finding = self._validate_reference(
                        "Finding", finding_id, findings, run_id, f"PRD section {section.id}", errors
                    )
                    if (
                        finding is not None
                        and finding.status == FindingEvidenceStatus.UNSUPPORTED
                        and not section.assumption
                    ):
                        errors.append(
                            f"UNSUPPORTED_FINDING: PRD section {section.id} presents {finding_id} as fact."
                        )
                for requirement_id in section.requirement_ids:
                    requirement = self._validate_reference(
                        "Requirement",
                        requirement_id,
                        requirements,
                        run_id,
                        f"PRD section {section.id}",
                        errors,
                    )
                    if (
                        requirement is not None
                        and requirement.validation_result == ArtifactValidationStatus.REJECTED
                    ):
                        errors.append(
                            f"REJECTED_REQUIREMENT_REFERENCE: PRD section {section.id} cites {requirement_id}."
                        )
                if section.assumption:
                    item_warnings.append(f"PRD section {section.id} is an explicit assumption.")
        hard_failures.extend(errors)
        warnings.extend(item_warnings)
        validations.append(
            self._validation(
                run_id,
                "VAL-TRACE-PRD-0001",
                "PRDArtifact",
                target_id,
                errors,
                item_warnings,
            )
        )

    @staticmethod
    def _prd_sections(structured) -> List[object]:
        return [
            *structured.user_problems,
            *structured.findings_summary,
            *structured.requirements,
            *structured.release_plan,
            *structured.acceptance_criteria,
            structured.evidence_summary,
        ]

    @staticmethod
    def _artifact_dispositions(result: IngestionResult) -> List[ArtifactValidationStatus]:
        planning = result.product_planning
        if planning is None:
            return []
        values = [
            *(item.disposition for item in planning.requirement_validations),
            *(item.disposition for item in planning.test_case_validations),
        ]
        for validation in (
            planning.version_plan_validation,
            planning.prd_validation,
        ):
            if validation is not None:
                values.append(validation.disposition)
        return values

    @staticmethod
    def _build_matrix(
        run_id: str,
        findings: Sequence[Finding],
        requirements: Sequence[Requirement],
        tests: Sequence[TestCase],
        version_plan,
    ) -> List[TraceabilityMatrixRow]:
        requirements_by_finding: Dict[str, List[Requirement]] = {}
        for requirement in requirements:
            if requirement.validation_result == ArtifactValidationStatus.REJECTED:
                continue
            for finding_id in requirement.finding_ids:
                requirements_by_finding.setdefault(finding_id, []).append(requirement)
        tests_by_requirement: Dict[str, List[TestCase]] = {}
        for test_case in tests:
            if test_case.validation_result != ArtifactValidationStatus.REJECTED:
                tests_by_requirement.setdefault(test_case.requirement_id, []).append(test_case)
        version_by_requirement = {
            requirement_id: item.version
            for item in (version_plan.items if version_plan else [])
            for requirement_id in item.requirement_ids
        }
        rows: List[TraceabilityMatrixRow] = []
        seen: Set[Tuple[object, ...]] = set()
        for finding in findings:
            evidence = [
                *((review_id, EvidenceRole.SUPPORTING) for review_id in finding.supporting_review_ids),
                *((review_id, EvidenceRole.CONFLICTING) for review_id in finding.conflicting_review_ids),
            ]
            if not evidence:
                evidence = [(None, None)]
            downstream = requirements_by_finding.get(finding.id) or [None]
            for review_id, role in evidence:
                for requirement in downstream:
                    linked_tests = (
                        tests_by_requirement.get(requirement.id) or [None]
                        if requirement is not None
                        else [None]
                    )
                    for test_case in linked_tests:
                        key = (
                            review_id,
                            finding.id,
                            requirement.id if requirement else None,
                            version_by_requirement.get(requirement.id) if requirement else None,
                            test_case.id if test_case else None,
                            role,
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append(
                            TraceabilityMatrixRow(
                                analysis_run_id=run_id,
                                review_id=review_id,
                                finding_id=finding.id,
                                requirement_id=requirement.id if requirement else None,
                                version=version_by_requirement.get(requirement.id) if requirement else None,
                                test_case_id=test_case.id if test_case else None,
                                evidence_role=role,
                                finding_status=finding.status,
                                requirement_validation=(
                                    requirement.validation_result if requirement else None
                                ),
                                test_validation=(test_case.validation_result if test_case else None),
                            )
                        )
        return rows

    @staticmethod
    def _build_forward(
        run_id: str,
        reviews: Dict[str, object],
        matrix: Sequence[TraceabilityMatrixRow],
    ) -> List[ForwardTraceability]:
        result: List[ForwardTraceability] = []
        for review_id in reviews:
            rows = [item for item in matrix if item.review_id == review_id]
            result.append(
                ForwardTraceability(
                    analysis_run_id=run_id,
                    review_id=review_id,
                    finding_ids=_stable(item.finding_id for item in rows if item.finding_id),
                    requirement_ids=_stable(
                        item.requirement_id for item in rows if item.requirement_id
                    ),
                    test_case_ids=_stable(item.test_case_id for item in rows if item.test_case_id),
                )
            )
        return result

    @staticmethod
    def _build_reverse(
        run_id: str,
        requirements: Sequence[Requirement],
        tests: Sequence[TestCase],
    ) -> List[ReverseTraceability]:
        requirement_by_id = {item.id: item for item in requirements}
        return [
            ReverseTraceability(
                analysis_run_id=run_id,
                test_case_id=test_case.id,
                requirement_id=test_case.requirement_id,
                finding_ids=(
                    list(requirement_by_id[test_case.requirement_id].finding_ids)
                    if test_case.requirement_id in requirement_by_id
                    else []
                ),
                review_ids=list(test_case.source_review_ids),
            )
            for test_case in tests
            if test_case.validation_result != ArtifactValidationStatus.REJECTED
        ]
