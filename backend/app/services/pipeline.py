from datetime import datetime, timezone
from typing import List, Optional

from app.models import (
    AnalysisOutputLanguage,
    AnalysisRunStatus,
    ArtifactValidationStatus,
    IngestionResult,
    PipelineStage,
    RunAuditEvent,
    RunAuditEventType,
)
from app.services.evidence import EvidenceValidationError, EvidenceValidationService
from app.services.product_planning import ProductPlanningError, ProductPlanningService
from app.services.semantic import (
    SemanticAnalysisError,
    SemanticAnalysisService,
    resolve_output_language,
)
from app.services.traceability import FinalTraceabilityValidator
from app.storage import RunStore


class FullPipelineError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class FullPipelineService:
    """Thin sequential orchestrator over the existing persisted stage services."""

    def __init__(
        self,
        store: RunStore,
        semantic_service: SemanticAnalysisService,
        evidence_service: EvidenceValidationService,
        product_service: ProductPlanningService,
    ) -> None:
        self.store = store
        self.semantic_service = semantic_service
        self.evidence_service = evidence_service
        self.product_service = product_service

    def queue(
        self,
        analysis_run_id: str,
        *,
        output_language: Optional[AnalysisOutputLanguage],
        ui_language: Optional[str],
    ) -> IngestionResult:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise FullPipelineError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        if not result.reviews:
            raise FullPipelineError("NO_VALID_REVIEWS", "No cleaned Reviews are available.")
        if result.run.status in {AnalysisRunStatus.PENDING, AnalysisRunStatus.RUNNING}:
            raise FullPipelineError(
                "RUN_ALREADY_ACTIVE",
                "This analysis run already has an active background stage.",
                status_code=409,
            )
        selected_language = output_language or result.run.output_language
        resolved_language = resolve_output_language(selected_language, ui_language)
        events = self._baseline_events(result)
        queued_run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.PENDING,
                "current_stage": PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
                "progress": 0,
                "output_language": selected_language,
                "resolved_output_language": resolved_language,
                "errors": [],
                "error_code": None,
                "finished_at": None,
            }
        )
        queued = result.model_copy(
            update={
                "run": queued_run,
                "semantic_analysis": None,
                "evidence_validation": None,
                "product_planning": None,
                "final_traceability": None,
                "audit_events": events,
            }
        )
        self.store.save(queued)
        self._append_event(
            analysis_run_id,
            RunAuditEventType.STAGE_STARTED,
            PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
            "Runtime semantic analysis started.",
        )
        return self._require(analysis_run_id)

    def execute(
        self,
        analysis_run_id: str,
        *,
        output_language: AnalysisOutputLanguage,
        ui_language: Optional[str],
    ) -> IngestionResult:
        try:
            self.semantic_service.analyze(
                analysis_run_id,
                output_language=output_language,
                ui_language=ui_language,
            )
            self._complete_stages(
                analysis_run_id,
                [
                    PipelineStage.SEMANTIC_TOPIC_DISCOVERY,
                    PipelineStage.FINDING_EXTRACTION,
                    PipelineStage.TOPIC_CONSOLIDATION,
                ],
            )
            self._append_event(
                analysis_run_id,
                RunAuditEventType.STAGE_STARTED,
                PipelineStage.EVIDENCE_VALIDATION,
                "Evidence validation started.",
            )
            self.evidence_service.validate(analysis_run_id)
            self._complete_stages(
                analysis_run_id,
                [
                    PipelineStage.EVIDENCE_VALIDATION,
                    PipelineStage.CONFLICT_ANALYSIS,
                    PipelineStage.FINDING_FINALIZATION,
                ],
            )
            self._append_event(
                analysis_run_id,
                RunAuditEventType.STAGE_STARTED,
                PipelineStage.REQUIREMENT_GENERATION,
                "Grounded product planning started.",
            )
            self.product_service.generate(analysis_run_id)
            self._complete_stages(
                analysis_run_id,
                [
                    PipelineStage.REQUIREMENT_GENERATION,
                    PipelineStage.VERSION_PLANNING,
                    PipelineStage.PRD_GENERATION,
                    PipelineStage.TEST_CASE_GENERATION,
                ],
            )
            self._append_event(
                analysis_run_id,
                RunAuditEventType.STAGE_STARTED,
                PipelineStage.TRACEABILITY_VALIDATION,
                "Final end-to-end traceability validation started.",
            )
            latest = self._require(analysis_run_id)
            active_run = latest.run.model_copy(
                update={
                    "status": AnalysisRunStatus.RUNNING,
                    "current_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "progress": 99,
                    "finished_at": None,
                }
            )
            latest = latest.model_copy(update={"run": active_run})
            self.store.save(latest)
            validator = FinalTraceabilityValidator(
                artifact_owner=lambda kind, identifier: self.store.find_artifact_owner(
                    kind,
                    identifier,
                    excluding_analysis_run_id=analysis_run_id,
                )
            )
            traceability = validator.validate(latest)
            latest = self._require(analysis_run_id).model_copy(
                update={"final_traceability": traceability}
            )
            self.store.save(latest)
            self._record_artifact_audit(analysis_run_id, latest)
            if traceability.coverage.hard_failures:
                message = "Final traceability validation found structural hard failures."
                self._append_event(
                    analysis_run_id,
                    RunAuditEventType.ERROR,
                    PipelineStage.TRACEABILITY_VALIDATION,
                    message,
                    details={"hard_failures": traceability.coverage.hard_failures},
                )
                latest = self._require(analysis_run_id)
                failed_run = latest.run.model_copy(
                    update={
                        "status": AnalysisRunStatus.VALIDATION_FAILED,
                        "current_stage": PipelineStage.TRACEABILITY_VALIDATION,
                        "last_successful_stage": PipelineStage.TEST_CASE_GENERATION,
                        "progress": 100,
                        "errors": [*latest.run.errors, *traceability.coverage.hard_failures],
                        "error_code": "FINAL_TRACEABILITY_VALIDATION_FAILED",
                        "finished_at": datetime.now(timezone.utc),
                    }
                )
                failed = latest.model_copy(update={"run": failed_run})
                self.store.save(failed)
                return failed
            self._append_event(
                analysis_run_id,
                RunAuditEventType.VALIDATION,
                PipelineStage.TRACEABILITY_VALIDATION,
                "Final traceability validation passed with no hard failure.",
                artifact_type="FinalTraceabilityResult",
                artifact_id=traceability.id,
                details={
                    "overall_coverage": traceability.coverage.overall_traceability_coverage,
                    "warning_count": len(traceability.coverage.warnings),
                },
            )
            self._append_event(
                analysis_run_id,
                RunAuditEventType.STAGE_COMPLETED,
                PipelineStage.TRACEABILITY_VALIDATION,
                "Final traceability validation completed.",
            )
            latest = self._require(analysis_run_id)
            warnings = list(dict.fromkeys(traceability.coverage.warnings))
            completed_run = latest.run.model_copy(
                update={
                    "status": (
                        AnalysisRunStatus.COMPLETED_WITH_WARNINGS
                        if warnings
                        else AnalysisRunStatus.COMPLETED
                    ),
                    "current_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "last_successful_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "progress": 100,
                    "warnings": warnings,
                    "errors": [],
                    "error_code": None,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            completed = latest.model_copy(update={"run": completed_run})
            self.store.save(completed)
            return completed
        except (SemanticAnalysisError, EvidenceValidationError, ProductPlanningError) as error:
            latest = self._require(analysis_run_id)
            self._append_event(
                analysis_run_id,
                RunAuditEventType.ERROR,
                latest.run.current_stage,
                error.message,
                details={"code": error.code},
            )
            raise FullPipelineError(
                error.code,
                error.message,
                status_code=error.status_code,
            ) from error

    def validate_existing(self, analysis_run_id: str) -> IngestionResult:
        result = self._require(analysis_run_id)
        validator = FinalTraceabilityValidator(
            artifact_owner=lambda kind, identifier: self.store.find_artifact_owner(
                kind, identifier, excluding_analysis_run_id=analysis_run_id
            )
        )
        traceability = validator.validate(result)
        updated = result.model_copy(update={"final_traceability": traceability})
        self.store.save(updated)
        return updated

    def _require(self, analysis_run_id: str) -> IngestionResult:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise FullPipelineError("RUN_NOT_FOUND", "Analysis run was not found.", status_code=404)
        return result

    @staticmethod
    def _event(
        run_id: str,
        index: int,
        event_type: RunAuditEventType,
        stage: PipelineStage,
        message: str,
        *,
        artifact_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> RunAuditEvent:
        return RunAuditEvent(
            id=f"AUD-{index:05d}",
            analysis_run_id=run_id,
            event_type=event_type,
            stage=stage,
            message=message,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            details=details or {},
        )

    def _baseline_events(self, result: IngestionResult) -> List[RunAuditEvent]:
        stages = [
            (PipelineStage.SCOPE_RESOLUTION, "Analysis scope resolved."),
            (PipelineStage.DATA_ACQUISITION, "Review data acquisition completed."),
            (PipelineStage.CLEANING_AND_NORMALIZATION, "Review cleaning and normalization completed."),
        ]
        return [
            self._event(
                result.analysis_run_id,
                index,
                RunAuditEventType.STAGE_COMPLETED,
                stage,
                message,
                details={
                    "clean_review_count": len(result.reviews),
                    "source": result.provider.source,
                },
            )
            for index, (stage, message) in enumerate(stages, start=1)
        ]

    def _append_event(
        self,
        run_id: str,
        event_type: RunAuditEventType,
        stage: PipelineStage,
        message: str,
        *,
        artifact_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        result = self._require(run_id)
        events = [
            *result.audit_events,
            self._event(
                run_id,
                len(result.audit_events) + 1,
                event_type,
                stage,
                message,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                details=details,
            ),
        ]
        self.store.save(result.model_copy(update={"audit_events": events}))

    def _complete_stages(self, run_id: str, stages: List[PipelineStage]) -> None:
        for stage in stages:
            self._append_event(
                run_id,
                RunAuditEventType.STAGE_COMPLETED,
                stage,
                f"{stage.value} completed.",
            )

    def _record_artifact_audit(self, run_id: str, result: IngestionResult) -> None:
        planning = result.product_planning
        if planning is None:
            return
        validations = [
            *planning.requirement_validations,
            *planning.test_case_validations,
            *(
                [planning.version_plan_validation]
                if planning.version_plan_validation is not None
                else []
            ),
            *([planning.prd_validation] if planning.prd_validation is not None else []),
        ]
        for validation in validations:
            if validation.disposition not in {
                ArtifactValidationStatus.REVISED,
                ArtifactValidationStatus.REJECTED,
                ArtifactValidationStatus.ASSUMPTION,
            }:
                continue
            event_type = (
                RunAuditEventType.REJECTION
                if validation.disposition == ArtifactValidationStatus.REJECTED
                else RunAuditEventType.REVISION
            )
            self._append_event(
                run_id,
                event_type,
                PipelineStage.TRACEABILITY_VALIDATION,
                f"{validation.target_type} {validation.target_id} was {validation.disposition.value.lower()}.",
                artifact_type=validation.target_type,
                artifact_id=validation.target_id,
                details={"disposition": validation.disposition.value},
            )
