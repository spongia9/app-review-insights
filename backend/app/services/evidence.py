import json
from datetime import datetime, timezone
from math import ceil
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError, create_llm_provider
from app.models import (
    AnalysisRunStatus,
    EvidenceJudgment,
    EvidenceJudgmentOutput,
    EvidenceMetrics,
    EvidenceStance,
    EvidenceStrength,
    EvidenceValidationAudit,
    EvidenceValidationBatch,
    EvidenceValidationResult,
    EvidenceValidationSummary,
    Finding,
    FindingCandidate,
    FindingEvidenceStatus,
    FindingValidationMetadata,
    IngestionResult,
    PipelineStage,
    Review,
)
from app.prompts import load_prompt
from app.storage import RunStore


OutputT = TypeVar("OutputT", bound=BaseModel)


class EvidenceValidationError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def create_evidence_batches(reviews: Sequence[Review], batch_size: int) -> List[List[Review]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    return [list(reviews[index : index + batch_size]) for index in range(0, len(reviews), batch_size)]


def validate_candidate_evidence_scope(
    candidate: FindingCandidate,
    *,
    analysis_run_id: str,
    current_run_review_ids: Set[str],
    cross_run_owner: Callable[[str], Optional[str]],
) -> None:
    if candidate.analysis_run_id != analysis_run_id:
        raise EvidenceValidationError(
            "CROSS_RUN_REFERENCE",
            f"Finding Candidate {candidate.id} belongs to another analysis run.",
        )
    review_ids = candidate.supporting_review_ids
    if len(review_ids) != len(set(review_ids)):
        raise EvidenceValidationError(
            "DUPLICATE_REVIEW_ID",
            f"Finding Candidate {candidate.id} contains duplicate Review IDs.",
        )
    for review_id in review_ids:
        if review_id in current_run_review_ids:
            continue
        owner = cross_run_owner(review_id)
        if owner:
            raise EvidenceValidationError(
                "CROSS_RUN_REFERENCE",
                f"Finding Candidate {candidate.id} references Review {review_id} from {owner}.",
            )
        raise EvidenceValidationError(
            "INVALID_REVIEW_ID",
            f"Finding Candidate {candidate.id} references unknown Review ID {review_id}.",
        )


def normalize_judgments(
    judgments: Sequence[EvidenceJudgment],
    relevance_threshold: float,
) -> Tuple[List[EvidenceJudgment], List[str]]:
    normalized: List[EvidenceJudgment] = []
    revisions: List[str] = []
    for judgment in judgments:
        if (
            judgment.stance in {EvidenceStance.SUPPORTS, EvidenceStance.CONFLICTS}
            and judgment.semantic_relevance < relevance_threshold
        ):
            revisions.append(
                f"Review {judgment.review_id} was reclassified from {judgment.stance.value} "
                f"to IRRELEVANT because relevance {judgment.semantic_relevance:.2f} was below "
                f"{relevance_threshold:.2f}."
            )
            normalized.append(judgment.model_copy(update={"stance": EvidenceStance.IRRELEVANT}))
        else:
            normalized.append(judgment)
    return normalized, revisions


def calculate_evidence_outcome(
    judgments: Sequence[EvidenceJudgment],
    settings: Settings,
) -> Tuple[EvidenceMetrics, FindingEvidenceStatus, float, EvidenceStrength]:
    supports = [item for item in judgments if item.stance == EvidenceStance.SUPPORTS]
    conflicts = [item for item in judgments if item.stance == EvidenceStance.CONFLICTS]
    neutrals = [item for item in judgments if item.stance == EvidenceStance.NEUTRAL]
    irrelevant = [item for item in judgments if item.stance == EvidenceStance.IRRELEVANT]
    directional_count = len(supports) + len(conflicts)
    relevant_count = directional_count + len(neutrals)
    support_ratio = len(supports) / directional_count if directional_count else 0.0
    conflict_ratio = len(conflicts) / directional_count if directional_count else 0.0
    evidence_density = directional_count / len(judgments) if judgments else 0.0
    average_support_relevance = (
        sum(item.semantic_relevance for item in supports) / len(supports)
        if supports
        else 0.0
    )
    metrics = EvidenceMetrics(
        validated_review_count=len(judgments),
        relevant_review_count=relevant_count,
        support_count=len(supports),
        conflict_count=len(conflicts),
        neutral_count=len(neutrals),
        irrelevant_count=len(irrelevant),
        support_ratio=round(support_ratio, 4),
        conflict_ratio=round(conflict_ratio, 4),
        evidence_density=round(evidence_density, 4),
        average_support_relevance=round(average_support_relevance, 4),
    )

    if not supports:
        status = FindingEvidenceStatus.UNSUPPORTED
    elif len(supports) < settings.evidence_min_relevant_reviews:
        status = FindingEvidenceStatus.INSUFFICIENT
    elif (
        len(supports) >= settings.evidence_conflict_min_count
        and len(conflicts) >= settings.evidence_conflict_min_count
        and conflict_ratio >= settings.evidence_conflict_ratio_threshold
    ):
        status = FindingEvidenceStatus.CONFLICTED
    elif (
        len(supports) >= settings.evidence_supported_min_count
        and support_ratio >= settings.evidence_supported_min_ratio
        and average_support_relevance >= settings.evidence_semantic_relevance_threshold
    ):
        status = FindingEvidenceStatus.SUPPORTED
    else:
        status = FindingEvidenceStatus.WEAK

    sample_factor = min(1.0, directional_count / settings.evidence_confidence_sample_cap)
    raw_confidence = (
        0.40 * average_support_relevance
        + 0.30 * support_ratio
        + 0.20 * sample_factor
        + 0.10 * evidence_density
        - 0.20 * conflict_ratio
    )
    status_cap = {
        FindingEvidenceStatus.WEAK: settings.evidence_weak_confidence_cap,
        FindingEvidenceStatus.CONFLICTED: settings.evidence_conflicted_confidence_cap,
        FindingEvidenceStatus.INSUFFICIENT: settings.evidence_insufficient_confidence_cap,
        FindingEvidenceStatus.UNSUPPORTED: settings.evidence_unsupported_confidence_cap,
    }.get(status, 1.0)
    confidence = round(max(0.0, min(status_cap, raw_confidence)), 4)

    if (
        status == FindingEvidenceStatus.SUPPORTED
        and len(supports) >= settings.evidence_high_strength_min_count
        and confidence >= settings.evidence_high_strength_min_confidence
    ):
        strength = EvidenceStrength.HIGH
    elif (
        status in {
            FindingEvidenceStatus.SUPPORTED,
            FindingEvidenceStatus.WEAK,
            FindingEvidenceStatus.CONFLICTED,
        }
        and directional_count >= settings.evidence_supported_min_count
        and confidence >= settings.evidence_medium_strength_min_confidence
    ):
        strength = EvidenceStrength.MEDIUM
    else:
        strength = EvidenceStrength.LOW
    return metrics, status, confidence, strength


class EvidenceValidationService:
    def __init__(
        self,
        settings: Settings,
        store: RunStore,
        provider_factory: Callable[[Settings], LLMProvider] = create_llm_provider,
    ) -> None:
        self.settings = settings
        self.store = store
        self.provider_factory = provider_factory

    def queue(
        self,
        analysis_run_id: str,
        *,
        candidate_ids: Optional[Sequence[str]] = None,
    ) -> IngestionResult:
        result, candidates = self._require_phase3_result(analysis_run_id, candidate_ids)
        if result.run.status in {AnalysisRunStatus.PENDING, AnalysisRunStatus.RUNNING}:
            raise EvidenceValidationError(
                "RUN_ALREADY_ACTIVE",
                "This analysis run already has an active background stage.",
                status_code=409,
            )
        run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.PENDING,
                "current_stage": PipelineStage.EVIDENCE_VALIDATION,
                "progress": 0,
                "errors": [],
                "error_code": None,
                "finished_at": None,
            }
        )
        queued = result.model_copy(
            update={"run": run, "evidence_validation": None, "product_planning": None}
        )
        self.store.save(queued)
        return queued

    def validate(
        self,
        analysis_run_id: str,
        *,
        candidate_ids: Optional[Sequence[str]] = None,
    ) -> IngestionResult:
        result, candidates = self._require_phase3_result(analysis_run_id, candidate_ids)
        revisions = list(result.run.revisions)
        provider: Optional[LLMProvider] = None
        run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "current_stage": PipelineStage.EVIDENCE_VALIDATION,
                "progress": 3,
                "errors": [],
                "error_code": None,
                "finished_at": None,
            }
        )
        result = result.model_copy(
            update={"run": run, "evidence_validation": None, "product_planning": None}
        )
        self.store.save(result)

        try:
            review_by_id = {review.id: review for review in result.reviews}
            for candidate in candidates:
                validate_candidate_evidence_scope(
                    candidate,
                    analysis_run_id=analysis_run_id,
                    current_run_review_ids=set(review_by_id),
                    cross_run_owner=lambda review_id: self.store.find_review_owner(
                        review_id, excluding_analysis_run_id=analysis_run_id
                    ),
                )
            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.EVIDENCE_VALIDATION,
                    "current_stage": PipelineStage.CONFLICT_ANALYSIS,
                    "progress": 8,
                }
            )
            result = result.model_copy(update={"run": run})
            self.store.save(result)

            provider = self.provider_factory(self.settings)
            run = run.model_copy(
                update={
                    "model_provider": provider.provider_name,
                    "model_name": provider.model_name,
                }
            )
            result = result.model_copy(update={"run": run})
            self.store.save(result)

            findings: List[Finding] = []
            audits: List[EvidenceValidationAudit] = []
            unique_validated_ids: Set[str] = set()
            total_batches = 0
            for index, candidate in enumerate(candidates, start=1):
                pool_reviews, pool_limited = self._build_validation_pool(result, candidate)
                judgments, validation_batches, candidate_revisions = self._validate_candidate_batches(
                    result,
                    candidate,
                    pool_reviews,
                    provider,
                )
                revisions.extend(candidate_revisions)
                normalized, relevance_revisions = normalize_judgments(
                    judgments,
                    self.settings.evidence_semantic_relevance_threshold,
                )
                revisions.extend(relevance_revisions)
                finding, audit = self._finalize_candidate(
                    result,
                    candidate,
                    normalized,
                    validation_batches,
                    provider,
                    pool_limited=pool_limited,
                    revisions=[*candidate_revisions, *relevance_revisions],
                )
                findings.append(finding)
                audits.append(audit)
                unique_validated_ids.update(audit.validation_review_ids)
                total_batches += len(validation_batches)
                partial = EvidenceValidationResult(
                    analysis_run_id=analysis_run_id,
                    total_candidate_count=len(candidates),
                    validated_candidate_count=len(findings),
                    validated_review_count=len(unique_validated_ids),
                    batch_count=total_batches,
                    batch_size=self.settings.evidence_batch_size,
                    model_provider=provider.provider_name,
                    model_name=provider.model_name,
                    findings=findings,
                    audits=audits,
                    validation_time=datetime.now(timezone.utc),
                )
                progress = 8 + int(82 * index / max(1, len(candidates)))
                latest_run = run.model_copy(
                    update={
                        "current_stage": PipelineStage.CONFLICT_ANALYSIS,
                        "progress": progress,
                        "revisions": list(revisions),
                    }
                )
                result = result.model_copy(update={"run": latest_run, "evidence_validation": partial})
                self.store.save(result)
                run = latest_run

            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.CONFLICT_ANALYSIS,
                    "current_stage": PipelineStage.FINDING_FINALIZATION,
                    "progress": 95,
                }
            )
            result = result.model_copy(update={"run": run})
            self.store.save(result)

            validation_time = datetime.now(timezone.utc)
            completed_validation = EvidenceValidationResult(
                analysis_run_id=analysis_run_id,
                total_candidate_count=len(candidates),
                validated_candidate_count=len(findings),
                validated_review_count=len(unique_validated_ids),
                batch_count=total_batches,
                batch_size=self.settings.evidence_batch_size,
                model_provider=provider.provider_name,
                model_name=provider.model_name,
                findings=findings,
                audits=audits,
                validation_time=validation_time,
            )
            warning_statuses = {
                FindingEvidenceStatus.WEAK,
                FindingEvidenceStatus.CONFLICTED,
                FindingEvidenceStatus.INSUFFICIENT,
                FindingEvidenceStatus.UNSUPPORTED,
            }
            has_evidence_warning = any(finding.status in warning_statuses for finding in findings)
            completed_run = run.model_copy(
                update={
                    "status": (
                        AnalysisRunStatus.WARNING
                        if result.run.warnings or has_evidence_warning or len(candidates) < self._candidate_count(result)
                        else AnalysisRunStatus.COMPLETED
                    ),
                    "current_stage": PipelineStage.FINDING_FINALIZATION,
                    "last_successful_stage": PipelineStage.FINDING_FINALIZATION,
                    "progress": 100,
                    "revisions": revisions,
                    "finished_at": validation_time,
                }
            )
            completed = result.model_copy(
                update={"run": completed_run, "evidence_validation": completed_validation}
            )
            self.store.save(completed)
            return completed
        except (LLMProviderError, EvidenceValidationError, ValidationError) as error:
            latest = self.store.get(analysis_run_id) or result
            message = getattr(error, "message", str(error))
            failed_run = latest.run.model_copy(
                update={
                    "status": AnalysisRunStatus.FAILED,
                    "progress": min(latest.run.progress, 99),
                    "errors": [*latest.run.errors, message],
                    "error_code": getattr(error, "code", "EVIDENCE_VALIDATION_FAILED"),
                    "revisions": revisions,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            self.store.save(latest.model_copy(update={"run": failed_run}))
            if isinstance(error, EvidenceValidationError):
                raise
            raise EvidenceValidationError(
                getattr(error, "code", "EVIDENCE_VALIDATION_FAILED"), message
            ) from error

    def _require_phase3_result(
        self,
        analysis_run_id: str,
        candidate_ids: Optional[Sequence[str]],
    ) -> Tuple[IngestionResult, List[FindingCandidate]]:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise EvidenceValidationError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        consolidated = result.semantic_analysis.consolidated_result if result.semantic_analysis else None
        if consolidated is None:
            raise EvidenceValidationError(
                "PHASE3_NOT_COMPLETE",
                "Phase 3 consolidated Finding Candidates are required before evidence validation.",
                status_code=409,
            )
        available = {candidate.id: candidate for candidate in consolidated.finding_candidates}
        if candidate_ids is None:
            selected = list(consolidated.finding_candidates)
        else:
            if len(candidate_ids) != len(set(candidate_ids)):
                raise EvidenceValidationError("DUPLICATE_CANDIDATE_ID", "Candidate IDs must be unique.")
            unknown = set(candidate_ids) - set(available)
            if unknown:
                raise EvidenceValidationError(
                    "INVALID_CANDIDATE_ID", f"Unknown Finding Candidate IDs: {sorted(unknown)}"
                )
            selected = [available[candidate_id] for candidate_id in candidate_ids]
        if not selected:
            raise EvidenceValidationError("NO_FINDING_CANDIDATES", "No Finding Candidates were selected.")
        return result, selected

    @staticmethod
    def _candidate_count(result: IngestionResult) -> int:
        consolidated = result.semantic_analysis.consolidated_result if result.semantic_analysis else None
        return len(consolidated.finding_candidates) if consolidated else 0

    def _build_validation_pool(
        self,
        result: IngestionResult,
        candidate: FindingCandidate,
    ) -> Tuple[List[Review], bool]:
        review_by_id = {review.id: review for review in result.reviews}
        candidate_ids = list(candidate.supporting_review_ids)
        candidate_set = set(candidate_ids)
        related_ids: List[str] = []
        consolidated = result.semantic_analysis.consolidated_result if result.semantic_analysis else None
        if consolidated:
            for topic in consolidated.topic_candidates:
                if candidate_set.intersection(topic.review_ids):
                    related_ids.extend(topic.review_ids)
            for other in consolidated.finding_candidates:
                if other.topic == candidate.topic or candidate_set.intersection(other.supporting_review_ids):
                    related_ids.extend(other.supporting_review_ids)
        deduplicated_related = [
            review_id
            for review_id in dict.fromkeys(related_ids)
            if review_id not in candidate_set and review_id in review_by_id
        ]
        extra_capacity = max(
            0, self.settings.evidence_conflict_pool_max_reviews - len(candidate_ids)
        )
        selected_related = deduplicated_related[:extra_capacity]
        limited = len(selected_related) < len(deduplicated_related)
        pool_ids = [*candidate_ids, *selected_related]
        return [review_by_id[review_id] for review_id in pool_ids], limited

    def _validate_candidate_batches(
        self,
        result: IngestionResult,
        candidate: FindingCandidate,
        pool_reviews: Sequence[Review],
        provider: LLMProvider,
    ) -> Tuple[List[EvidenceJudgment], List[EvidenceValidationBatch], List[str]]:
        all_judgments: List[EvidenceJudgment] = []
        batches: List[EvidenceValidationBatch] = []
        revisions: List[str] = []
        for index, reviews in enumerate(
            create_evidence_batches(pool_reviews, self.settings.evidence_batch_size), start=1
        ):
            batch_id = f"EV-{candidate.id}-{index:03d}"
            expected_ids = [review.id for review in reviews]
            output = self._call_with_retries(
                provider=provider,
                response_model=EvidenceJudgmentOutput,
                schema_name="EvidenceJudgmentOutput",
                system_prompt=load_prompt("evidence_validation.md"),
                user_prompt=self._evidence_prompt(result, candidate, batch_id, reviews),
                validator=lambda value, expected_ids=expected_ids: self._validate_output_scope(
                    value,
                    analysis_run_id=result.analysis_run_id,
                    candidate_id=candidate.id,
                    expected_review_ids=expected_ids,
                ),
                revisions=revisions,
                operation=f"evidence validation for {candidate.id} batch {index}",
            )
            batch = EvidenceValidationBatch(
                id=batch_id,
                analysis_run_id=result.analysis_run_id,
                finding_candidate_id=candidate.id,
                review_ids=expected_ids,
                judgments=output.judgments,
            )
            batches.append(batch)
            all_judgments.extend(output.judgments)
        return all_judgments, batches, revisions

    @staticmethod
    def _validate_output_scope(
        output: EvidenceJudgmentOutput,
        *,
        analysis_run_id: str,
        candidate_id: str,
        expected_review_ids: Sequence[str],
    ) -> None:
        if output.analysis_run_id != analysis_run_id:
            raise EvidenceValidationError(
                "CROSS_RUN_REFERENCE", "Evidence output referenced another analysis run."
            )
        if output.finding_candidate_id != candidate_id:
            raise EvidenceValidationError(
                "INVALID_CANDIDATE_ID", "Evidence output referenced another Finding Candidate."
            )
        returned_ids = [judgment.review_id for judgment in output.judgments]
        if len(returned_ids) != len(set(returned_ids)):
            raise EvidenceValidationError(
                "DUPLICATE_REVIEW_ID", "Evidence output returned duplicate Review IDs."
            )
        invalid = set(returned_ids) - set(expected_review_ids)
        missing = set(expected_review_ids) - set(returned_ids)
        if invalid:
            raise EvidenceValidationError(
                "INVALID_REVIEW_ID",
                "Evidence output referenced one or more unknown or out-of-batch Review IDs.",
            )
        if missing:
            raise EvidenceValidationError(
                "INCOMPLETE_EVIDENCE_OUTPUT",
                "Evidence output omitted one or more required Review IDs.",
            )
        for judgment in output.judgments:
            if judgment.analysis_run_id != analysis_run_id:
                raise EvidenceValidationError(
                    "CROSS_RUN_REFERENCE", "An Evidence Judgment referenced another analysis run."
                )
            if judgment.finding_candidate_id != candidate_id:
                raise EvidenceValidationError(
                    "INVALID_CANDIDATE_ID", "An Evidence Judgment referenced another candidate."
                )

    def _call_with_retries(
        self,
        *,
        provider: LLMProvider,
        response_model: Type[OutputT],
        schema_name: str,
        system_prompt: str,
        user_prompt: str,
        validator: Callable[[OutputT], None],
        revisions: List[str],
        operation: str,
    ) -> OutputT:
        last_error: Optional[Exception] = None
        for attempt in range(self.settings.llm_max_retries + 1):
            prompt = user_prompt
            if attempt and last_error:
                payload = json.loads(user_prompt)
                payload["correction"] = {
                    "reason": getattr(last_error, "code", type(last_error).__name__),
                    "message": getattr(last_error, "message", str(last_error)),
                    "instruction": (
                        "Return one complete JSON object. Include exactly one judgment for every "
                        "allowed Review ID and never create or omit identifiers."
                    ),
                }
                prompt = json.dumps(payload, ensure_ascii=False)
            try:
                output = provider.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    response_model=response_model,
                    schema_name=schema_name,
                )
                validator(output)
                return output
            except (LLMProviderError, EvidenceValidationError, ValidationError) as error:
                last_error = error
                revisions.append(
                    f"Attempt {attempt + 1} failed for {operation}: "
                    f"{getattr(error, 'code', type(error).__name__)}."
                )
                if isinstance(error, LLMProviderError) and not error.retryable:
                    break
                if attempt >= self.settings.llm_max_retries:
                    break
        if isinstance(last_error, (LLMProviderError, EvidenceValidationError)):
            raise last_error
        raise EvidenceValidationError(
            "INVALID_STRUCTURED_OUTPUT", f"Unable to complete {operation}."
        )

    def _finalize_candidate(
        self,
        result: IngestionResult,
        candidate: FindingCandidate,
        judgments: Sequence[EvidenceJudgment],
        validation_batches: Sequence[EvidenceValidationBatch],
        provider: LLMProvider,
        *,
        pool_limited: bool,
        revisions: List[str],
    ) -> Tuple[Finding, EvidenceValidationAudit]:
        metrics, status, confidence, strength = calculate_evidence_outcome(
            judgments, self.settings
        )
        grouped = {
            stance: [item.review_id for item in judgments if item.stance == stance]
            for stance in EvidenceStance
        }
        validation_time = datetime.now(timezone.utc)
        limitations = self._actual_limitations(
            result,
            validated_count=len(judgments),
            pool_limited=pool_limited,
        )
        uncertainty = self._uncertainty_text(
            result,
            status=status,
            metrics=metrics,
        )
        audit_id = f"EVA-{uuid4().hex[:12].upper()}"
        audit = EvidenceValidationAudit(
            id=audit_id,
            analysis_run_id=result.analysis_run_id,
            finding_candidate_id=candidate.id,
            candidate_review_ids=list(candidate.supporting_review_ids),
            validation_review_ids=[judgment.review_id for judgment in judgments],
            supporting_review_ids=grouped[EvidenceStance.SUPPORTS],
            conflicting_review_ids=grouped[EvidenceStance.CONFLICTS],
            neutral_review_ids=grouped[EvidenceStance.NEUTRAL],
            irrelevant_review_ids=grouped[EvidenceStance.IRRELEVANT],
            judgments=list(judgments),
            validation_batches=list(validation_batches),
            status=status,
            confidence=confidence,
            evidence_strength=strength,
            metrics=metrics,
            uncertainty=uncertainty,
            limitations=limitations,
            model_provider=provider.provider_name,
            model_name=provider.model_name,
            validation_time=validation_time,
            revisions=revisions,
        )
        metadata = FindingValidationMetadata(
            analysis_run_id=result.analysis_run_id,
            audit_id=audit_id,
            finding_candidate_id=candidate.id,
            metrics=metrics,
            validated_review_count=len(judgments),
            batch_count=len(validation_batches),
            eligible_for_requirement_generation=status == FindingEvidenceStatus.SUPPORTED,
            validation_time=validation_time,
        )
        finding = Finding(
            id=f"F-{candidate.id}",
            analysis_run_id=result.analysis_run_id,
            topic=candidate.topic,
            title=candidate.title,
            problem=candidate.problem,
            summary=candidate.summary,
            supporting_review_ids=grouped[EvidenceStance.SUPPORTS],
            conflicting_review_ids=grouped[EvidenceStance.CONFLICTS],
            support_count=len(grouped[EvidenceStance.SUPPORTS]),
            conflict_count=len(grouped[EvidenceStance.CONFLICTS]),
            evidence_strength=strength,
            confidence=confidence,
            status=status,
            uncertainty=uncertainty,
            limitations=limitations,
            validation_metadata=metadata,
        )
        return finding, audit

    def _actual_limitations(
        self,
        result: IngestionResult,
        *,
        validated_count: int,
        pool_limited: bool,
    ) -> List[str]:
        chinese = result.run.resolved_output_language.value == "zh-CN"
        limitations = list(dict.fromkeys(result.provider.source_limitations))
        if result.provider.is_live_collection and result.provider.storefront == "us":
            limitations.append(
                "仅包含美国区店面评论，不能代表其他地区用户。"
                if chinese
                else "U.S. storefront only; results do not represent other storefronts."
            )
        limitations.append(
            (
                f"本洞察验证了 {validated_count}/{len(result.reviews)} 条清洗后评论；"
                "冲突发现限定在候选证据与模型生成的相关主题证据池内。"
            )
            if chinese
            else (
                f"This finding validated {validated_count}/{len(result.reviews)} cleaned Reviews; "
                "conflict discovery was bounded to candidate evidence and the model-derived Topic pool."
            )
        )
        if pool_limited:
            limitations.append(
                "相关主题证据池超过配置上限，额外冲突候选按稳定顺序截断。"
                if chinese
                else "The related Topic evidence pool exceeded the configured cap; additional conflict candidates were deterministically bounded."
            )
        missing_language = sum(review.language is None for review in result.reviews)
        if missing_language:
            limitations.append(
                f"{missing_language} 条评论缺少语言元数据。"
                if chinese
                else f"{missing_language} Reviews are missing language metadata."
            )
        missing_version = sum(review.version is None for review in result.reviews)
        if missing_version:
            limitations.append(
                f"{missing_version} 条评论缺少应用版本元数据。"
                if chinese
                else f"{missing_version} Reviews are missing app-version metadata."
            )
        return list(dict.fromkeys(limitations))

    @staticmethod
    def _uncertainty_text(
        result: IngestionResult,
        *,
        status: FindingEvidenceStatus,
        metrics: EvidenceMetrics,
    ) -> str:
        chinese = result.run.resolved_output_language.value == "zh-CN"
        if chinese:
            if status == FindingEvidenceStatus.UNSUPPORTED:
                return (
                    f"在 {metrics.validated_review_count} 条已验证评论中没有发现可靠支持；"
                    f"其中 {metrics.conflict_count} 条与候选主张冲突。"
                )
            if status == FindingEvidenceStatus.INSUFFICIENT:
                return (
                    f"仅有 {metrics.support_count} 条评论支持该主张，"
                    "证据量不足以形成可靠结论。"
                )
            if status == FindingEvidenceStatus.CONFLICTED:
                return (
                    f"{metrics.support_count} 条评论支持、{metrics.conflict_count} 条评论冲突，"
                    f"冲突占方向性证据的 {metrics.conflict_ratio:.0%}。"
                )
            if status == FindingEvidenceStatus.WEAK:
                return (
                    f"目前仅有 {metrics.support_count} 条评论支持该主张，"
                    f"虽支持比例为 {metrics.support_ratio:.0%}，但证据量或代表性仍低于充分标准。"
                )
            return (
                f"{metrics.support_count} 条评论支持该主张，支持比例为 {metrics.support_ratio:.0%}；"
                f"验证池中仍有 {metrics.neutral_count + metrics.irrelevant_count} 条中立或无关反馈。"
            )
        if status == FindingEvidenceStatus.UNSUPPORTED:
            return (
                f"No reliable support was found in {metrics.validated_review_count} validated Reviews; "
                f"{metrics.conflict_count} conflicted with the candidate claim."
            )
        if status == FindingEvidenceStatus.INSUFFICIENT:
            return (
                f"Only {metrics.support_count} Review supports the claim, which is too sparse "
                "for a reliable conclusion."
            )
        if status == FindingEvidenceStatus.CONFLICTED:
            return (
                f"{metrics.support_count} Reviews support and {metrics.conflict_count} conflict; "
                f"conflicts represent {metrics.conflict_ratio:.0%} of directional evidence."
            )
        if status == FindingEvidenceStatus.WEAK:
            return (
                f"Only {metrics.support_count} Reviews currently support the claim. Although the "
                f"support ratio is {metrics.support_ratio:.0%}, volume or representativeness remains below the sufficient threshold."
            )
        return (
            f"{metrics.support_count} Reviews support the claim at a {metrics.support_ratio:.0%} support ratio; "
            f"{metrics.neutral_count + metrics.irrelevant_count} validated Reviews were neutral or irrelevant."
        )

    @staticmethod
    def _review_payload(reviews: Sequence[Review]) -> List[Dict[str, object]]:
        return [
            {
                "id": review.id,
                "rating": review.rating,
                "title": review.title,
                "text": review.text,
                "version": review.version,
                "language": review.language,
                "date": review.created_at.isoformat() if review.created_at else None,
            }
            for review in reviews
        ]

    def _evidence_prompt(
        self,
        result: IngestionResult,
        candidate: FindingCandidate,
        batch_id: str,
        reviews: Sequence[Review],
    ) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "finding_candidate_id": candidate.id,
            "batch_id": batch_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": result.run.resolved_output_language.value,
            "claim": {
                "topic": candidate.topic,
                "title": candidate.title,
                "problem": candidate.problem,
                "summary": candidate.summary,
            },
            "allowed_review_ids": [review.id for review in reviews],
            "reviews": self._review_payload(reviews),
            "json_schema": EvidenceJudgmentOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)


def evidence_summary(evidence: EvidenceValidationResult) -> EvidenceValidationSummary:
    return EvidenceValidationSummary(
        analysis_run_id=evidence.analysis_run_id,
        total_candidate_count=evidence.total_candidate_count,
        validated_candidate_count=evidence.validated_candidate_count,
        validated_review_count=evidence.validated_review_count,
        batch_count=evidence.batch_count,
        batch_size=evidence.batch_size,
        finding_count=len(evidence.findings),
        rejected_candidate_count=sum(
            finding.status == FindingEvidenceStatus.UNSUPPORTED
            for finding in evidence.findings
        ),
        model_provider=evidence.model_provider,
        model_name=evidence.model_name,
        validation_time=evidence.validation_time,
    )
