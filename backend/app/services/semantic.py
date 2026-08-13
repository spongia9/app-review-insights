import json
from datetime import datetime, timezone
from math import ceil
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError, create_llm_provider
from app.models import (
    AnalysisOutputLanguage,
    AnalysisRunStatus,
    AuditArtifact,
    AuditArtifactType,
    BatchAnalysisResult,
    ConsolidatedAnalysisResult,
    FindingCandidate,
    FindingCandidateOutput,
    IngestionResult,
    PipelineStage,
    Review,
    SemanticAnalysisResult,
    SemanticAnalysisSummary,
    TopicCandidate,
    TopicDiscoveryOutput,
)
from app.prompts import load_prompt
from app.storage import RunStore


OutputT = TypeVar("OutputT", bound=BaseModel)


class SemanticAnalysisError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def create_review_batches(reviews: Sequence[Review], batch_size: int) -> List[List[Review]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    return [list(reviews[index : index + batch_size]) for index in range(0, len(reviews), batch_size)]


def resolve_output_language(
    output_language: AnalysisOutputLanguage,
    ui_language: Optional[str],
) -> AnalysisOutputLanguage:
    if output_language != AnalysisOutputLanguage.FOLLOW_UI:
        return output_language
    return (
        AnalysisOutputLanguage.EN_US
        if ui_language == AnalysisOutputLanguage.EN_US.value
        else AnalysisOutputLanguage.ZH_CN
    )


def _validate_topic_scope(
    topics: Sequence[TopicCandidate],
    *,
    analysis_run_id: str,
    allowed_review_ids: Set[str],
    allowed_batch_ids: Set[str],
) -> None:
    for topic in topics:
        if topic.analysis_run_id != analysis_run_id:
            raise SemanticAnalysisError("CROSS_RUN_REFERENCE", "Topic referenced another analysis run.")
        if topic.batch_id not in allowed_batch_ids:
            raise SemanticAnalysisError("INVALID_BATCH_REFERENCE", "Topic referenced a disallowed batch.")
        invalid = set(topic.review_ids) - allowed_review_ids
        if invalid:
            raise SemanticAnalysisError(
                "INVALID_REVIEW_ID",
                f"Topic referenced unknown or out-of-scope Review IDs: {sorted(invalid)}",
            )


def _validate_finding_scope(
    findings: Sequence[FindingCandidate],
    *,
    analysis_run_id: str,
    allowed_review_ids: Set[str],
    allowed_batch_ids: Set[str],
) -> None:
    for finding in findings:
        if finding.analysis_run_id != analysis_run_id:
            raise SemanticAnalysisError("CROSS_RUN_REFERENCE", "Finding Candidate referenced another analysis run.")
        invalid_reviews = set(finding.supporting_review_ids) - allowed_review_ids
        invalid_batches = set(finding.source_batch_ids) - allowed_batch_ids
        if invalid_reviews:
            raise SemanticAnalysisError(
                "INVALID_REVIEW_ID",
                f"Finding Candidate referenced unknown or out-of-scope Review IDs: {sorted(invalid_reviews)}",
            )
        if invalid_batches:
            raise SemanticAnalysisError(
                "INVALID_BATCH_REFERENCE",
                f"Finding Candidate referenced disallowed batch IDs: {sorted(invalid_batches)}",
            )


def validate_consolidation_lineage(
    consolidated: ConsolidatedAnalysisResult,
    batch_results: Sequence[BatchAnalysisResult],
) -> None:
    allowed_review_ids = {review_id for batch in batch_results for review_id in batch.review_ids}
    allowed_batch_ids = {batch.batch_id for batch in batch_results}
    _validate_topic_scope(
        consolidated.topic_candidates,
        analysis_run_id=consolidated.analysis_run_id,
        allowed_review_ids=allowed_review_ids,
        allowed_batch_ids=allowed_batch_ids,
    )
    _validate_finding_scope(
        consolidated.finding_candidates,
        analysis_run_id=consolidated.analysis_run_id,
        allowed_review_ids=allowed_review_ids,
        allowed_batch_ids=allowed_batch_ids,
    )
    review_batch_ids = {
        review_id: batch.batch_id
        for batch in batch_results
        for review_id in batch.review_ids
    }
    for finding in consolidated.finding_candidates:
        expected_batch_ids = {
            review_batch_ids[review_id]
            for review_id in finding.supporting_review_ids
        }
        if set(finding.source_batch_ids) != expected_batch_ids:
            raise SemanticAnalysisError(
                "LINEAGE_LOSS",
                f"Consolidated Finding {finding.id} does not preserve its Review-to-batch lineage.",
            )
    source_finding_review_ids = {
        review_id
        for batch in batch_results
        for finding in batch.finding_candidates
        for review_id in finding.supporting_review_ids
    }
    consolidated_review_ids = {
        review_id
        for finding in consolidated.finding_candidates
        for review_id in finding.supporting_review_ids
    }
    missing = source_finding_review_ids - consolidated_review_ids
    if missing:
        raise SemanticAnalysisError(
            "LINEAGE_LOSS",
            f"Consolidation dropped source Review IDs: {sorted(missing)}",
        )
    source_finding_batch_ids = {
        batch_id
        for batch in batch_results
        for finding in batch.finding_candidates
        for batch_id in finding.source_batch_ids
    }
    consolidated_finding_batch_ids = {
        batch_id
        for finding in consolidated.finding_candidates
        for batch_id in finding.source_batch_ids
    }
    missing_batch_ids = source_finding_batch_ids - consolidated_finding_batch_ids
    if missing_batch_ids:
        raise SemanticAnalysisError(
            "LINEAGE_LOSS",
            f"Consolidation dropped source batch IDs: {sorted(missing_batch_ids)}",
        )
    source_topic_review_ids = {
        review_id
        for batch in batch_results
        for topic in batch.topic_candidates
        for review_id in topic.review_ids
    }
    consolidated_topic_review_ids = {
        review_id for topic in consolidated.topic_candidates for review_id in topic.review_ids
    }
    missing_topics = source_topic_review_ids - consolidated_topic_review_ids
    if missing_topics:
        raise SemanticAnalysisError(
            "LINEAGE_LOSS",
            f"Consolidation dropped Topic source Review IDs: {sorted(missing_topics)}",
        )


class SemanticAnalysisService:
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
        output_language: Optional[AnalysisOutputLanguage],
        ui_language: Optional[str],
    ) -> IngestionResult:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise SemanticAnalysisError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        if not result.reviews:
            raise SemanticAnalysisError("NO_VALID_REVIEWS", "No cleaned reviews are available for semantic analysis.")
        selected_language = output_language or result.run.output_language
        resolved_language = resolve_output_language(selected_language, ui_language)
        run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.PENDING,
                "current_stage": PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
                "progress": 60,
                "output_language": selected_language,
                "resolved_output_language": resolved_language,
                "total_review_count": len(result.reviews),
                "model_provider": self.settings.llm_provider,
                "model_name": self.settings.llm_model,
                "analyzed_review_count": 0,
                "sampling_strategy": "NONE",
                "batch_count": ceil(len(result.reviews) / self.settings.llm_review_batch_size),
                "batch_size": self.settings.llm_review_batch_size,
                "errors": [],
                "finished_at": None,
            }
        )
        queued = result.model_copy(update={"run": run, "semantic_analysis": None})
        self.store.save(queued)
        return queued

    def analyze(
        self,
        analysis_run_id: str,
        *,
        output_language: AnalysisOutputLanguage,
        ui_language: Optional[str],
    ) -> IngestionResult:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise SemanticAnalysisError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        if not result.reviews:
            raise SemanticAnalysisError("NO_VALID_REVIEWS", "No cleaned reviews are available for semantic analysis.")

        resolved_language = resolve_output_language(output_language, ui_language)
        provider: Optional[LLMProvider] = None
        revisions = list(result.run.revisions)
        batches = create_review_batches(result.reviews, self.settings.llm_review_batch_size)
        run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "current_stage": PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
                "progress": 65,
                "output_language": output_language,
                "resolved_output_language": resolved_language,
                "total_review_count": len(result.reviews),
                "analyzed_review_count": 0,
                "sampling_strategy": "NONE",
                "batch_count": len(batches),
                "batch_size": self.settings.llm_review_batch_size,
                "finished_at": None,
                "errors": [],
                "revisions": revisions,
            }
        )
        result = result.model_copy(update={"run": run, "semantic_analysis": None})
        self.store.save(result)

        try:
            provider = self.provider_factory(self.settings)
            run = run.model_copy(
                update={
                    "model_provider": provider.provider_name,
                    "model_name": provider.model_name,
                }
            )
            result = result.model_copy(update={"run": run})
            self.store.save(result)
            semantic = self._run_batches(
                result,
                provider=provider,
                batches=batches,
                resolved_language=resolved_language,
                revisions=revisions,
            )
            completed_status = AnalysisRunStatus.WARNING if run.warnings else AnalysisRunStatus.COMPLETED
            completed_run = run.model_copy(
                update={
                    "status": completed_status,
                    "current_stage": PipelineStage.TOPIC_CONSOLIDATION,
                    "last_successful_stage": PipelineStage.TOPIC_CONSOLIDATION,
                    "progress": 100,
                    "analyzed_review_count": len(result.reviews),
                    "finished_at": semantic.analysis_time,
                    "revisions": revisions,
                }
            )
            completed = result.model_copy(update={"run": completed_run, "semantic_analysis": semantic})
            self.store.save(completed)
            return completed
        except (LLMProviderError, SemanticAnalysisError, ValidationError) as error:
            message = getattr(error, "message", str(error))
            latest = self.store.get(analysis_run_id) or result
            failed_run = latest.run.model_copy(
                update={
                    "status": AnalysisRunStatus.FAILED,
                    "progress": min(latest.run.progress, 95),
                    "errors": [*latest.run.errors, message],
                    "revisions": revisions,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            self.store.save(latest.model_copy(update={"run": failed_run}))
            if isinstance(error, SemanticAnalysisError):
                raise
            raise SemanticAnalysisError(getattr(error, "code", "SEMANTIC_ANALYSIS_FAILED"), message) from error

    def _run_batches(
        self,
        result: IngestionResult,
        *,
        provider: LLMProvider,
        batches: Sequence[Sequence[Review]],
        resolved_language: AnalysisOutputLanguage,
        revisions: List[str],
    ) -> SemanticAnalysisResult:
        run_id = result.analysis_run_id
        batch_results: List[BatchAnalysisResult] = []
        audit_artifacts: List[AuditArtifact] = []

        for index, reviews in enumerate(batches, start=1):
            batch_id = f"B{index:04d}"
            review_ids = {review.id for review in reviews}
            topics = self._call_with_retries(
                provider=provider,
                response_model=TopicDiscoveryOutput,
                schema_name="TopicDiscoveryOutput",
                system_prompt=load_prompt("topic_discovery.md"),
                user_prompt=self._topic_prompt(result, batch_id, reviews, resolved_language),
                validator=lambda output: _validate_topic_scope(
                    output.topics,
                    analysis_run_id=run_id,
                    allowed_review_ids=review_ids,
                    allowed_batch_ids={batch_id},
                ),
                revisions=revisions,
                operation=f"topic discovery for {batch_id}",
            )
            audit_artifacts.append(
                self._audit(run_id, AuditArtifactType.TOPIC_DRAFT, PipelineStage.SEMANTIC_TOPIC_DISCOVERY, topics, batch_id)
            )
            batch_results.append(
                BatchAnalysisResult(
                    analysis_run_id=run_id,
                    batch_id=batch_id,
                    review_ids=[review.id for review in reviews],
                    topic_candidates=topics.topics,
                )
            )
            self._persist_partial(
                result,
                batch_results,
                audit_artifacts,
                PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
                index,
                revisions,
            )

        self._mark_current_stage(run_id, PipelineStage.FINDING_EXTRACTION, 75)
        for index, (reviews, batch_result) in enumerate(zip(batches, batch_results), start=1):
            batch_id = batch_result.batch_id
            review_ids = set(batch_result.review_ids)
            finding_output = self._call_with_retries(
                provider=provider,
                response_model=FindingCandidateOutput,
                schema_name="FindingCandidateOutput",
                system_prompt=load_prompt("finding_candidate.md"),
                user_prompt=self._finding_prompt(
                    result,
                    batch_id,
                    reviews,
                    batch_result.topic_candidates,
                    resolved_language,
                ),
                validator=lambda output: _validate_finding_scope(
                    output.finding_candidates,
                    analysis_run_id=run_id,
                    allowed_review_ids=review_ids,
                    allowed_batch_ids={batch_id},
                ),
                revisions=revisions,
                operation=f"finding extraction for {batch_id}",
            )
            audit_artifacts.append(
                self._audit(run_id, AuditArtifactType.FINDING_DRAFT, PipelineStage.FINDING_EXTRACTION, finding_output, batch_id)
            )
            batch_results[index - 1] = batch_result.model_copy(
                update={"finding_candidates": finding_output.finding_candidates}
            )
            self._persist_partial(result, batch_results, audit_artifacts, PipelineStage.FINDING_EXTRACTION, index, revisions)

        self._mark_current_stage(run_id, PipelineStage.TOPIC_CONSOLIDATION, 92)
        consolidated = self._call_with_retries(
            provider=provider,
            response_model=ConsolidatedAnalysisResult,
            schema_name="ConsolidatedAnalysisResult",
            system_prompt=load_prompt("topic_consolidation.md"),
            user_prompt=self._consolidation_prompt(result, batch_results, resolved_language),
            validator=lambda output: validate_consolidation_lineage(output, batch_results),
            revisions=revisions,
            operation="cross-batch consolidation",
        )
        audit_artifacts.append(
            self._audit(run_id, AuditArtifactType.CONSOLIDATION_DRAFT, PipelineStage.TOPIC_CONSOLIDATION, consolidated)
        )
        return SemanticAnalysisResult(
            analysis_run_id=run_id,
            total_review_count=len(result.reviews),
            analyzed_review_count=len(result.reviews),
            batch_count=len(batch_results),
            batch_size=self.settings.llm_review_batch_size,
            sampling_strategy="NONE",
            model_provider=provider.provider_name,
            model_name=provider.model_name,
            analysis_goal=result.run.analysis_goal,
            output_language=result.run.output_language,
            resolved_output_language=resolved_language,
            batch_results=batch_results,
            consolidated_result=consolidated,
            audit_artifacts=audit_artifacts,
            analysis_time=datetime.now(timezone.utc),
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
            if attempt:
                correction = (
                    "The prior response was invalid. Re-check every ID allowlist and return valid JSON only."
                )
                try:
                    prompt_payload = json.loads(user_prompt)
                    prompt_payload["correction"] = correction
                    prompt = json.dumps(prompt_payload, ensure_ascii=False)
                except json.JSONDecodeError:
                    prompt += f"\n\nCORRECTION: {correction}"
            try:
                output = provider.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    response_model=response_model,
                    schema_name=schema_name,
                )
                validator(output)
                return output
            except (LLMProviderError, SemanticAnalysisError, ValidationError) as error:
                last_error = error
                revisions.append(f"Retry {attempt + 1} for {operation}: {getattr(error, 'code', type(error).__name__)}")
                if isinstance(error, LLMProviderError) and not error.retryable:
                    break
                if attempt >= self.settings.llm_max_retries:
                    break
        if isinstance(last_error, SemanticAnalysisError):
            raise last_error
        if isinstance(last_error, LLMProviderError):
            raise last_error
        raise SemanticAnalysisError("INVALID_STRUCTURED_OUTPUT", f"Unable to complete {operation}.")

    def _persist_partial(
        self,
        base_result: IngestionResult,
        batches: List[BatchAnalysisResult],
        artifacts: List[AuditArtifact],
        stage: PipelineStage,
        analyzed_batches: int,
        revisions: List[str],
    ) -> None:
        analyzed_count = sum(len(batch.review_ids) for batch in batches)
        semantic = SemanticAnalysisResult(
            analysis_run_id=base_result.analysis_run_id,
            total_review_count=len(base_result.reviews),
            analyzed_review_count=analyzed_count,
            batch_count=ceil(len(base_result.reviews) / self.settings.llm_review_batch_size),
            batch_size=self.settings.llm_review_batch_size,
            sampling_strategy="NONE",
            model_provider=base_result.run.model_provider or "unknown",
            model_name=base_result.run.model_name or "unknown",
            analysis_goal=base_result.run.analysis_goal,
            output_language=base_result.run.output_language,
            resolved_output_language=base_result.run.resolved_output_language,
            batch_results=list(batches),
            audit_artifacts=list(artifacts),
        )
        ratio = analyzed_batches / max(1, semantic.batch_count)
        progress = (
            65 + min(10, int(ratio * 10))
            if stage == PipelineStage.SEMANTIC_TOPIC_DISCOVERY
            else 75 + min(15, int(ratio * 15))
        )
        run = base_result.run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "current_stage": stage,
                "last_successful_stage": stage,
                "progress": progress,
                "analyzed_review_count": analyzed_count,
                "revisions": list(revisions),
            }
        )
        self.store.save(base_result.model_copy(update={"run": run, "semantic_analysis": semantic}))

    def _mark_current_stage(self, analysis_run_id: str, stage: PipelineStage, progress: int) -> None:
        latest = self.store.get(analysis_run_id)
        if latest is None:
            raise SemanticAnalysisError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        run = latest.run.model_copy(update={"current_stage": stage, "progress": progress})
        self.store.save(latest.model_copy(update={"run": run}))

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

    def _topic_prompt(self, result: IngestionResult, batch_id: str, reviews: Sequence[Review], language: AnalysisOutputLanguage) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "batch_id": batch_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": language.value,
            "allowed_review_ids": [review.id for review in reviews],
            "reviews": self._review_payload(reviews),
            "json_schema": TopicDiscoveryOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _finding_prompt(self, result: IngestionResult, batch_id: str, reviews: Sequence[Review], topics: Sequence[TopicCandidate], language: AnalysisOutputLanguage) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "batch_id": batch_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": language.value,
            "allowed_review_ids": [review.id for review in reviews],
            "allowed_batch_ids": [batch_id],
            "reviews": self._review_payload(reviews),
            "topics": [topic.model_dump(mode="json") for topic in topics],
            "json_schema": FindingCandidateOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _consolidation_prompt(self, result: IngestionResult, batches: Sequence[BatchAnalysisResult], language: AnalysisOutputLanguage) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": language.value,
            "allowed_review_ids": [review.id for review in result.reviews],
            "allowed_batch_ids": [batch.batch_id for batch in batches],
            "batch_results": [batch.model_dump(mode="json") for batch in batches],
            "json_schema": ConsolidatedAnalysisResult.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _audit(
        run_id: str,
        artifact_type: AuditArtifactType,
        stage: PipelineStage,
        payload: BaseModel,
        batch_id: Optional[str] = None,
    ) -> AuditArtifact:
        return AuditArtifact(
            id=f"AUD-{uuid4().hex[:12].upper()}",
            analysis_run_id=run_id,
            artifact_type=artifact_type,
            stage=stage,
            batch_id=batch_id,
            payload=payload.model_dump(mode="json"),
            created_at=datetime.now(timezone.utc),
        )


def semantic_summary(semantic: SemanticAnalysisResult) -> SemanticAnalysisSummary:
    consolidated = semantic.consolidated_result
    return SemanticAnalysisSummary(
        analysis_run_id=semantic.analysis_run_id,
        total_review_count=semantic.total_review_count,
        analyzed_review_count=semantic.analyzed_review_count,
        batch_count=semantic.batch_count,
        batch_size=semantic.batch_size,
        sampling_strategy=semantic.sampling_strategy,
        model_provider=semantic.model_provider,
        model_name=semantic.model_name,
        analysis_goal=semantic.analysis_goal,
        output_language=semantic.output_language,
        resolved_output_language=semantic.resolved_output_language,
        topic_count=len(consolidated.topic_candidates) if consolidated else 0,
        finding_candidate_count=len(consolidated.finding_candidates) if consolidated else 0,
        analysis_time=semantic.analysis_time,
    )
