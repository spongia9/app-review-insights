from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.core.config import Settings
from app.models import (
    AnalysisOutputLanguage,
    ArtifactValidationStatus,
    Finding,
    FindingEvidenceStatus,
    ImpactLevel,
    IngestionResult,
    PRDArtifact,
    PRDSection,
    Requirement,
    RequirementDraft,
    RequirementGenerationMetadata,
    RequirementGroundingDecision,
    RequirementGroundingVerdict,
    RequirementPriority,
    StructuredPRD,
    StructuredPRDDraft,
    TestCase,
    TestCaseDraft,
    TraceabilityCoverage,
    ValidationResult,
    VersionPlan,
    VersionPlanDraft,
    VersionPlanItem,
)


class ProductValidationError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def validate_findings_for_planning(
    result: IngestionResult,
    *,
    cross_run_owner: Callable[[str], Optional[str]],
) -> Tuple[List[Finding], List[Finding]]:
    evidence = result.evidence_validation
    if evidence is None or not evidence.findings:
        raise ProductValidationError(
            "PHASE4_NOT_COMPLETE",
            "Validated Findings are required before product planning.",
            status_code=409,
        )
    current_review_ids = {review.id for review in result.reviews}
    eligible: List[Finding] = []
    blocked: List[Finding] = []
    for finding in evidence.findings:
        if finding.analysis_run_id != result.analysis_run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE",
                f"Finding {finding.id} belongs to another analysis run.",
            )
        for review_id in [*finding.supporting_review_ids, *finding.conflicting_review_ids]:
            if review_id in current_review_ids:
                continue
            owner = cross_run_owner(review_id)
            code = "CROSS_RUN_REFERENCE" if owner else "INVALID_REVIEW_ID"
            raise ProductValidationError(
                code,
                f"Finding {finding.id} references an invalid current-run Review ID.",
            )
        if (
            finding.status == FindingEvidenceStatus.SUPPORTED
            and finding.validation_metadata.eligible_for_requirement_generation
        ):
            eligible.append(finding)
        else:
            blocked.append(finding)
    return eligible, blocked


def derive_requirement_review_ids(
    finding_ids: Sequence[str],
    finding_by_id: Dict[str, Finding],
) -> List[str]:
    review_ids: List[str] = []
    for finding_id in finding_ids:
        finding = finding_by_id.get(finding_id)
        if finding is None:
            raise ProductValidationError(
                "INVALID_FINDING_ID",
                f"Requirement references unknown Finding {finding_id}.",
            )
        review_ids.extend(finding.supporting_review_ids)
    inherited = list(dict.fromkeys(review_ids))
    if not inherited:
        raise ProductValidationError(
            "EMPTY_INHERITED_EVIDENCE",
            "A non-assumption Requirement must inherit supporting Review evidence.",
        )
    return inherited


def validate_acceptance_criteria(criteria: Sequence[str], settings: Settings) -> List[str]:
    normalized = [item.strip() for item in criteria]
    if len(normalized) < settings.product_acceptance_criteria_min_count:
        raise ProductValidationError(
            "INVALID_ACCEPTANCE_CRITERIA",
            "A Requirement needs the configured minimum number of Acceptance Criteria.",
        )
    if any(len(item) < settings.product_acceptance_criterion_min_chars for item in normalized):
        raise ProductValidationError(
            "INVALID_ACCEPTANCE_CRITERIA",
            "Acceptance Criteria must be specific enough to be observable.",
        )
    if len(normalized) != len(set(normalized)):
        raise ProductValidationError(
            "INVALID_ACCEPTANCE_CRITERIA",
            "Acceptance Criteria must be unique.",
        )
    return normalized


def recommend_priority(
    findings: Sequence[Finding],
    impact: ImpactLevel,
    settings: Settings,
    *,
    assumption: bool = False,
    output_language: AnalysisOutputLanguage = AnalysisOutputLanguage.EN_US,
) -> Tuple[RequirementPriority, str, float]:
    total_support = sum(finding.support_count for finding in findings)
    weight = max(1, total_support)
    confidence = sum(
        (finding.confidence or 0.0) * max(1, finding.support_count)
        for finding in findings
    ) / weight
    all_supported = all(finding.status == FindingEvidenceStatus.SUPPORTED for finding in findings)
    if assumption:
        priority = RequirementPriority.P3
    elif not all_supported:
        priority = RequirementPriority.P2
    elif (
        impact == ImpactLevel.HIGH
        and total_support >= settings.product_p0_min_support_count
        and confidence >= settings.product_p0_min_confidence
    ):
        priority = RequirementPriority.P0
    elif (
        impact in {ImpactLevel.HIGH, ImpactLevel.MEDIUM}
        and total_support >= settings.product_p1_min_support_count
        and confidence >= settings.product_p1_min_confidence
    ):
        priority = RequirementPriority.P1
    else:
        priority = RequirementPriority.P2
    chinese = output_language == AnalysisOutputLanguage.ZH_CN
    reason = (
        f"代码依据 {total_support} 条支持证据、校准置信度 {confidence:.0%}、"
        f"证据状态与 {impact.value} 用户影响推荐 {priority.value}。"
        if chinese
        else (
            f"Code recommends {priority.value} from {total_support} supporting Reviews, "
            f"{confidence:.0%} calibrated confidence, evidence status, and {impact.value} user impact."
        )
    )
    return priority, reason, round(max(0.0, min(1.0, confidence)), 4)


def validate_grounding_decisions(
    decisions: Sequence[RequirementGroundingDecision],
    drafts: Sequence[RequirementDraft],
    analysis_run_id: str,
) -> Dict[str, RequirementGroundingDecision]:
    draft_ids = [draft.id for draft in drafts]
    returned_ids = [decision.requirement_draft_id for decision in decisions]
    if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != set(draft_ids):
        raise ProductValidationError(
            "INVALID_REQUIREMENT_VALIDATION",
            "Requirement grounding decisions must exactly cover the current draft allowlist.",
        )
    if any(decision.analysis_run_id != analysis_run_id for decision in decisions):
        raise ProductValidationError(
            "CROSS_RUN_REFERENCE",
            "A Requirement grounding decision belongs to another analysis run.",
        )
    return {decision.requirement_draft_id: decision for decision in decisions}


def finalize_requirements(
    drafts: Sequence[RequirementDraft],
    decisions: Sequence[RequirementGroundingDecision],
    findings: Sequence[Finding],
    settings: Settings,
    *,
    provider_name: str,
    model_name: str,
    generated_at: datetime,
    output_language: AnalysisOutputLanguage,
) -> Tuple[List[Requirement], List[ValidationResult]]:
    finding_by_id = {finding.id: finding for finding in findings}
    decision_by_id = validate_grounding_decisions(
        decisions, drafts, drafts[0].analysis_run_id
    )
    requirements: List[Requirement] = []
    validations: List[ValidationResult] = []
    for index, draft in enumerate(drafts, start=1):
        if any(finding_id not in finding_by_id for finding_id in draft.finding_ids):
            raise ProductValidationError(
                "INVALID_FINDING_ID",
                f"Requirement draft {draft.id} references a disallowed Finding.",
            )
        decision = decision_by_id[draft.id]
        validation_id = f"VAL-REQ-{index:04d}"
        if decision.verdict == RequirementGroundingVerdict.UNGROUNDED:
            validations.append(
                ValidationResult(
                    id=validation_id,
                    analysis_run_id=draft.analysis_run_id,
                    target_type="RequirementDraft",
                    target_id=draft.id,
                    disposition=ArtifactValidationStatus.REJECTED,
                    errors=[decision.reason],
                )
            )
            continue
        revised = decision.verdict == RequirementGroundingVerdict.PARTIAL
        use_revision = revised or not decision.acceptance_criteria_testable
        title = decision.revised_title if use_revision else draft.title
        user_problem = decision.revised_user_problem if use_revision else draft.user_problem
        description = decision.revised_description if use_revision else draft.description
        criteria = (
            decision.revised_acceptance_criteria
            if use_revision
            else draft.acceptance_criteria
        )
        if not all([title, user_problem, description, criteria]):
            raise ProductValidationError(
                "INVALID_REQUIREMENT_REVISION",
                f"Requirement draft {draft.id} cannot be safely revised.",
            )
        normalized_criteria = validate_acceptance_criteria(criteria, settings)
        inherited_review_ids = derive_requirement_review_ids(draft.finding_ids, finding_by_id)
        source_findings = [finding_by_id[finding_id] for finding_id in draft.finding_ids]
        priority, priority_reason, confidence = recommend_priority(
            source_findings,
            draft.impact,
            settings,
            assumption=draft.assumption,
            output_language=output_language,
        )
        priority_adjusted = priority != draft.proposed_priority
        disposition = (
            ArtifactValidationStatus.ASSUMPTION
            if draft.assumption
            else ArtifactValidationStatus.REVISED
            if revised or priority_adjusted or not decision.acceptance_criteria_testable
            else ArtifactValidationStatus.ACCEPTED
        )
        warnings: List[str] = []
        if priority_adjusted:
            warnings.append(
                f"Model priority {draft.proposed_priority.value} was calibrated to {priority.value}."
            )
        requirement = Requirement(
            id=f"REQ-{index:04d}",
            analysis_run_id=draft.analysis_run_id,
            title=title,
            user_problem=user_problem,
            description=description,
            finding_ids=list(draft.finding_ids),
            review_ids=inherited_review_ids,
            priority=priority,
            recommended_priority=priority,
            final_priority=priority,
            priority_reason=priority_reason,
            impact=draft.impact,
            confidence=confidence,
            acceptance_criteria=normalized_criteria,
            target_version=draft.target_version,
            assumption=draft.assumption,
            validation_result=disposition,
            generated_by="runtime_llm",
            generation_metadata=RequirementGenerationMetadata(
                analysis_run_id=draft.analysis_run_id,
                draft_id=draft.id,
                validation_id=validation_id,
                grounding_verdict=decision.verdict,
                generated_by="runtime_llm",
                model_provider=provider_name,
                model_name=model_name,
                generated_at=generated_at,
                priority_adjusted=priority_adjusted,
            ),
        )
        requirements.append(requirement)
        validations.append(
            ValidationResult(
                id=validation_id,
                analysis_run_id=draft.analysis_run_id,
                target_type="RequirementDraft",
                target_id=draft.id,
                disposition=disposition,
                warnings=[decision.reason, *warnings],
                revision_of=draft.id if disposition == ArtifactValidationStatus.REVISED else None,
            )
        )
    return requirements, validations


def finalize_version_plan(
    draft: VersionPlanDraft,
    requirements: Sequence[Requirement],
    *,
    provider_name: str,
    model_name: str,
) -> Tuple[VersionPlan, List[Requirement]]:
    allowed = {
        requirement.id
        for requirement in requirements
        if requirement.validation_result
        in {ArtifactValidationStatus.ACCEPTED, ArtifactValidationStatus.REVISED}
    }
    assigned = [requirement_id for item in draft.items for requirement_id in item.requirement_ids]
    if len(assigned) != len(set(assigned)):
        raise ProductValidationError(
            "DUPLICATE_VERSION_REQUIREMENT",
            "A Requirement cannot appear in more than one version.",
        )
    if set(assigned) != allowed:
        raise ProductValidationError(
            "INCOMPLETE_VERSION_PLAN",
            "VersionPlan must assign every accepted/revised Requirement exactly once.",
        )
    items = [
        VersionPlanItem(
            id=f"VPI-{index:03d}",
            analysis_run_id=draft.analysis_run_id,
            version=item.version,
            theme=item.theme,
            goal=item.goal,
            requirement_ids=list(item.requirement_ids),
            rationale=item.rationale,
            dependencies=list(item.dependencies),
            risk=item.risk,
            scope_note=item.scope_note,
            validation_result=ArtifactValidationStatus.ACCEPTED,
        )
        for index, item in enumerate(draft.items, start=1)
    ]
    plan = VersionPlan(
        id="VP-0001",
        analysis_run_id=draft.analysis_run_id,
        title=draft.title,
        summary=draft.summary,
        items=items,
        validation_result=ArtifactValidationStatus.ACCEPTED,
        generated_by="runtime_llm",
        model_provider=provider_name,
        model_name=model_name,
        generated_at=draft.generated_at,
    )
    version_by_requirement = {
        requirement_id: item.version
        for item in items
        for requirement_id in item.requirement_ids
    }
    updated_requirements = [
        requirement.model_copy(
            update={"target_version": version_by_requirement.get(requirement.id)}
        )
        for requirement in requirements
    ]
    return plan, updated_requirements


def _prd_section(
    *,
    index: int,
    run_id: str,
    section_type: str,
    title: str,
    content: str,
    finding_ids: Optional[List[str]] = None,
    requirement_ids: Optional[List[str]] = None,
    version_item_ids: Optional[List[str]] = None,
    assumption: bool = False,
) -> PRDSection:
    return PRDSection(
        id=f"PRDS-{index:04d}",
        analysis_run_id=run_id,
        section_type=section_type,
        title=title,
        content=content,
        finding_ids=finding_ids or [],
        requirement_ids=requirement_ids or [],
        version_item_ids=version_item_ids or [],
        assumption=assumption,
        validation_result=(
            ArtifactValidationStatus.ASSUMPTION
            if assumption
            else ArtifactValidationStatus.ACCEPTED
        ),
    )


def finalize_structured_prd(
    draft: StructuredPRDDraft,
    result: IngestionResult,
    findings: Sequence[Finding],
    requirements: Sequence[Requirement],
    version_plan: VersionPlan,
) -> StructuredPRD:
    if draft.version_plan_id != version_plan.id:
        raise ProductValidationError(
            "INVALID_VERSION_REFERENCE", "Structured PRD references another VersionPlan."
        )
    finding_by_id = {finding.id: finding for finding in findings}
    requirement_by_id = {
        requirement.id: requirement
        for requirement in requirements
        if requirement.validation_result != ArtifactValidationStatus.REJECTED
    }
    version_by_id = {item.id: item for item in version_plan.items}
    for section in [
        *draft.user_problems,
        *draft.findings_summary,
        *draft.requirements,
        *draft.release_plan,
        *draft.acceptance_criteria,
    ]:
        for finding_id in section.finding_ids:
            finding = finding_by_id.get(finding_id)
            if finding is None or finding.status == FindingEvidenceStatus.UNSUPPORTED:
                raise ProductValidationError(
                    "PRD_UNSUPPORTED_REFERENCE",
                    "Structured PRD references an unknown or unsupported Finding.",
                )
        if set(section.requirement_ids) - set(requirement_by_id):
            raise ProductValidationError(
                "PRD_REJECTED_REQUIREMENT_REFERENCE",
                "Structured PRD references an unknown or rejected Requirement.",
            )
        if set(section.version_item_ids) - set(version_by_id):
            raise ProductValidationError(
                "INVALID_VERSION_REFERENCE",
                "Structured PRD references an unknown VersionPlan item.",
            )
    run_id = result.analysis_run_id
    section_index = 1

    def next_section(**kwargs: object) -> PRDSection:
        nonlocal section_index
        section = _prd_section(index=section_index, run_id=run_id, **kwargs)
        section_index += 1
        return section

    user_problems = [
        next_section(
            section_type="USER_PROBLEM",
            title=finding.title,
            content=finding.problem,
            finding_ids=[finding.id],
        )
        for finding in findings
        if finding.status != FindingEvidenceStatus.UNSUPPORTED
    ]
    findings_summary = [
        next_section(
            section_type="FINDING_SUMMARY",
            title=finding.title,
            content=finding.summary,
            finding_ids=[finding.id],
        )
        for finding in findings
        if finding.status != FindingEvidenceStatus.UNSUPPORTED
    ]
    requirement_sections = [
        next_section(
            section_type="REQUIREMENT",
            title=requirement.title,
            content=requirement.description,
            finding_ids=list(requirement.finding_ids),
            requirement_ids=[requirement.id],
            assumption=requirement.assumption,
        )
        for requirement in requirements
        if requirement.validation_result != ArtifactValidationStatus.REJECTED
    ]
    release_sections = [
        next_section(
            section_type="RELEASE_PLAN",
            title=f"{item.version} — {item.theme}",
            content=f"{item.goal} {item.rationale}",
            requirement_ids=list(item.requirement_ids),
            version_item_ids=[item.id],
        )
        for item in version_plan.items
    ]
    acceptance_sections = [
        next_section(
            section_type="ACCEPTANCE_CRITERIA",
            title=requirement.title,
            content="\n".join(f"- {criterion}" for criterion in requirement.acceptance_criteria),
            finding_ids=list(requirement.finding_ids),
            requirement_ids=[requirement.id],
        )
        for requirement in requirements
        if requirement.validation_result
        in {ArtifactValidationStatus.ACCEPTED, ArtifactValidationStatus.REVISED}
    ]
    known_limitations = list(
        dict.fromkeys(
            [
                *result.provider.source_limitations,
                *(limitation for finding in findings for limitation in finding.limitations),
            ]
        )
    )
    assumptions = [
        requirement.description for requirement in requirements if requirement.assumption
    ]
    chinese = result.run.resolved_output_language == AnalysisOutputLanguage.ZH_CN
    background = (
        f"本规划基于当前分析任务中的 {len(result.reviews)} 条清洗后用户评论和 "
        f"{len(findings)} 个已验证洞察。"
        if chinese
        else (
            f"This plan is based on {len(result.reviews)} cleaned Reviews and "
            f"{len(findings)} validated Findings from the current analysis run."
        )
    )
    analysis_goal = (result.run.analysis_goal or ("未指定" if chinese else "not specified")).rstrip("。.!！?？")
    analysis_scope = (
        f"数据源：{result.provider.source}；分析结果语言：{result.run.resolved_output_language.value}；"
        f"分析目标：{analysis_goal}。"
        if chinese
        else (
            f"Source: {result.provider.source}; output language: "
            f"{result.run.resolved_output_language.value}; analysis goal: "
            f"{analysis_goal}."
        )
    )
    evidence_content = (
        f"{sum(finding.support_count for finding in findings)} 条支持证据支撑 "
        f"{len(findings)} 个洞察，并派生 {len(requirements)} 个产品需求。"
        if chinese
        else (
            f"{sum(finding.support_count for finding in findings)} supporting evidence links "
            f"ground {len(findings)} Findings and {len(requirements)} derived Requirements."
        )
    )
    evidence_summary = next_section(
        section_type="EVIDENCE_SUMMARY",
        title="证据摘要" if chinese else "Evidence Summary",
        content=evidence_content,
        finding_ids=[finding.id for finding in findings],
        requirement_ids=[requirement.id for requirement in requirements],
    )
    return StructuredPRD(
        id="PRD-0001",
        analysis_run_id=run_id,
        title=draft.title,
        product_goal=draft.product_goal,
        background=background,
        analysis_scope=analysis_scope,
        user_problems=user_problems,
        findings_summary=findings_summary,
        requirements=requirement_sections,
        release_plan=release_sections,
        acceptance_criteria=acceptance_sections,
        assumptions=assumptions,
        limitations=known_limitations,
        evidence_summary=evidence_summary,
        version_plan_id=version_plan.id,
        validation_result=ArtifactValidationStatus.REVISED,
    )


def finalize_test_cases(
    drafts: Sequence[TestCaseDraft],
    requirements: Sequence[Requirement],
    settings: Settings,
    *,
    provider_name: str,
    model_name: str,
) -> Tuple[List[TestCase], List[ValidationResult]]:
    allowed = {
        requirement.id: requirement
        for requirement in requirements
        if requirement.validation_result
        in {ArtifactValidationStatus.ACCEPTED, ArtifactValidationStatus.REVISED}
    }
    referenced = {draft.requirement_id for draft in drafts}
    if referenced != set(allowed):
        raise ProductValidationError(
            "INCOMPLETE_TEST_COVERAGE",
            "TestCase drafts must cover every accepted/revised Requirement.",
        )
    tests: List[TestCase] = []
    validations: List[ValidationResult] = []
    for index, draft in enumerate(drafts, start=1):
        requirement = allowed.get(draft.requirement_id)
        if requirement is None:
            raise ProductValidationError(
                "INVALID_REQUIREMENT_ID",
                f"TestCase draft {draft.id} references an invalid Requirement.",
            )
        if len(draft.steps) < 2 or len(draft.expected_result.strip()) < settings.product_acceptance_criterion_min_chars:
            raise ProductValidationError(
                "INVALID_TEST_CASE_QUALITY",
                f"TestCase draft {draft.id} is not observable or testable.",
            )
        priority_adjusted = draft.proposed_priority != requirement.final_priority
        disposition = (
            ArtifactValidationStatus.REVISED
            if priority_adjusted
            else ArtifactValidationStatus.ACCEPTED
        )
        tests.append(
            TestCase(
                id=f"TC-{index:04d}",
                analysis_run_id=draft.analysis_run_id,
                requirement_id=requirement.id,
                source_review_ids=list(requirement.review_ids),
                title=draft.title,
                preconditions=list(draft.preconditions),
                steps=list(draft.steps),
                expected_result=draft.expected_result,
                test_type=draft.test_type,
                priority=requirement.final_priority,
                validation_result=disposition,
                generated_by="runtime_llm",
                model_provider=provider_name,
                model_name=model_name,
                generated_at=draft.generated_at,
                draft_id=draft.id,
            )
        )
        validations.append(
            ValidationResult(
                id=f"VAL-TC-{index:04d}",
                analysis_run_id=draft.analysis_run_id,
                target_type="TestCaseDraft",
                target_id=draft.id,
                disposition=disposition,
                warnings=(
                    ["TestCase priority was inherited from its Requirement."]
                    if priority_adjusted
                    else []
                ),
                revision_of=draft.id if priority_adjusted else None,
            )
        )
    return tests, validations


def calculate_traceability(
    result: IngestionResult,
    findings: Sequence[Finding],
    requirements: Sequence[Requirement],
    test_cases: Sequence[TestCase],
) -> TraceabilityCoverage:
    run_id = result.analysis_run_id
    current_reviews = {review.id for review in result.reviews}
    finding_by_id = {finding.id: finding for finding in findings}
    requirement_by_id = {requirement.id: requirement for requirement in requirements}
    hard_failures: List[str] = []
    warnings: List[str] = []
    finding_valid = 0
    for finding in findings:
        valid = (
            finding.analysis_run_id == run_id
            and bool(finding.supporting_review_ids)
            and set(finding.supporting_review_ids).issubset(current_reviews)
            and not set(finding.supporting_review_ids).intersection(finding.conflicting_review_ids)
        )
        finding_valid += int(valid)
        if not valid:
            hard_failures.append(f"Finding {finding.id} has invalid evidence lineage.")
        if finding.status in {
            FindingEvidenceStatus.WEAK,
            FindingEvidenceStatus.CONFLICTED,
            FindingEvidenceStatus.INSUFFICIENT,
            FindingEvidenceStatus.UNSUPPORTED,
        }:
            warnings.append(f"Finding {finding.id} has status {finding.status.value}.")
    traceable_requirements = 0
    applicable_requirements = [requirement for requirement in requirements if not requirement.assumption]
    for requirement in applicable_requirements:
        try:
            inherited = derive_requirement_review_ids(requirement.finding_ids, finding_by_id)
        except ProductValidationError as error:
            hard_failures.append(error.message)
            continue
        valid = (
            requirement.analysis_run_id == run_id
            and set(requirement.review_ids) == set(inherited)
            and set(requirement.review_ids).issubset(current_reviews)
        )
        traceable_requirements += int(valid)
        if not valid:
            hard_failures.append(f"Requirement {requirement.id} has broken evidence inheritance.")
    traceable_tests = 0
    for test_case in test_cases:
        requirement = requirement_by_id.get(test_case.requirement_id)
        valid = (
            test_case.analysis_run_id == run_id
            and requirement is not None
            and set(test_case.source_review_ids) == set(requirement.review_ids)
            and set(test_case.source_review_ids).issubset(current_reviews)
        )
        traceable_tests += int(valid)
        if not valid:
            hard_failures.append(f"TestCase {test_case.id} has broken Requirement evidence inheritance.")
    tested_requirement_ids = {test_case.requirement_id for test_case in test_cases}
    for requirement in applicable_requirements:
        if requirement.id not in tested_requirement_ids:
            warnings.append(f"Requirement {requirement.id} has no TestCase coverage.")
    finding_denominator = len(findings)
    requirement_denominator = len(applicable_requirements)
    test_case_denominator = len(test_cases)
    numerator = finding_valid + traceable_requirements + traceable_tests
    denominator = finding_denominator + requirement_denominator + test_case_denominator

    def coverage(count: int, total: int) -> Optional[float]:
        return round(count / total, 4) if total else None

    return TraceabilityCoverage(
        analysis_run_id=run_id,
        finding_evidence_coverage=coverage(finding_valid, finding_denominator),
        requirement_traceability_coverage=coverage(
            traceable_requirements, requirement_denominator
        ),
        test_case_traceability_coverage=coverage(traceable_tests, test_case_denominator),
        overall_traceability_coverage=coverage(numerator, denominator),
        finding_denominator=finding_denominator,
        requirement_denominator=requirement_denominator,
        test_case_denominator=test_case_denominator,
        hard_failures=list(dict.fromkeys(hard_failures)),
        warnings=list(dict.fromkeys(warnings)),
    )
