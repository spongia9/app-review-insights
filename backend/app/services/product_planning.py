import json
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import LLMProvider, LLMProviderError, create_llm_provider
from app.models import (
    AnalysisRunStatus,
    ArtifactValidationStatus,
    Finding,
    IngestionResult,
    PipelineStage,
    PRDArtifact,
    ProductPlanningResult,
    ProductPlanningSummary,
    Requirement,
    RequirementDraft,
    RequirementDraftOutput,
    RequirementGroundingDecision,
    RequirementGroundingOutput,
    StructuredPRDDraft,
    StructuredPRDDraftOutput,
    TestCaseDraft,
    TestCaseDraftOutput,
    ValidationResult,
    VersionPlanDraft,
    VersionPlanDraftOutput,
    VersionPlan,
)
from app.prompts import load_prompt
from app.services.prd_renderer import render_prd_markdown
from app.services.product_rules import (
    ProductValidationError,
    calculate_traceability,
    finalize_requirements,
    finalize_structured_prd,
    finalize_test_cases,
    finalize_version_plan,
    validate_acceptance_criteria,
    validate_findings_for_planning,
)
from app.storage import RunStore


OutputT = TypeVar("OutputT", bound=BaseModel)


class ProductPlanningError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProductPlanningService:
    def __init__(
        self,
        settings: Settings,
        store: RunStore,
        provider_factory: Callable[[Settings], LLMProvider] = create_llm_provider,
    ) -> None:
        self.settings = settings
        self.store = store
        self.provider_factory = provider_factory

    def queue(self, analysis_run_id: str) -> IngestionResult:
        result, _, _ = self._require_phase4_result(analysis_run_id)
        if result.run.status in {AnalysisRunStatus.PENDING, AnalysisRunStatus.RUNNING}:
            raise ProductPlanningError(
                "RUN_ALREADY_ACTIVE",
                "This analysis run already has an active background stage.",
                status_code=409,
            )
        queued_run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.PENDING,
                "current_stage": PipelineStage.REQUIREMENT_GENERATION,
                "progress": 0,
                "errors": [],
                "error_code": None,
                "finished_at": None,
            }
        )
        queued = result.model_copy(update={"run": queued_run})
        self.store.save(queued)
        return queued

    def generate(self, analysis_run_id: str) -> IngestionResult:
        result, eligible_findings, blocked_findings = self._require_phase4_result(
            analysis_run_id
        )
        revisions = list(result.run.revisions)
        run = result.run.model_copy(
            update={
                "status": AnalysisRunStatus.RUNNING,
                "current_stage": PipelineStage.REQUIREMENT_GENERATION,
                "progress": 3,
                "errors": [],
                "error_code": None,
                "finished_at": None,
            }
        )
        result = result.model_copy(update={"run": run})
        self.store.save(result)
        provider: Optional[LLMProvider] = None
        try:
            provider = self.provider_factory(self.settings)
            planning = ProductPlanningResult(
                analysis_run_id=analysis_run_id,
                model_provider=provider.provider_name,
                model_name=provider.model_name,
            )
            run = run.model_copy(
                update={
                    "model_provider": provider.provider_name,
                    "model_name": provider.model_name,
                }
            )
            result = result.model_copy(update={"run": run, "product_planning": planning})
            self.store.save(result)

            generated_at = datetime.now(timezone.utc)
            requirement_drafts = self._generate_requirement_drafts(
                result, eligible_findings, provider, revisions, generated_at
            )
            grounding_decisions = self._validate_requirement_grounding(
                result, eligible_findings, requirement_drafts, provider, revisions
            )
            requirements, requirement_validations = finalize_requirements(
                requirement_drafts,
                grounding_decisions,
                eligible_findings,
                self.settings,
                provider_name=provider.provider_name,
                model_name=provider.model_name,
                generated_at=generated_at,
                output_language=result.run.resolved_output_language,
            )
            planning = planning.model_copy(
                update={
                    "requirement_drafts": requirement_drafts,
                    "requirement_validations": requirement_validations,
                    "requirements": requirements,
                }
            )
            result = result.model_copy(update={"product_planning": planning})
            self.store.save(result)
            if not requirements:
                raise ProductValidationError(
                    "NO_VALID_REQUIREMENTS",
                    "All Requirement drafts were rejected by grounding validation.",
                )
            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.REQUIREMENT_GENERATION,
                    "current_stage": PipelineStage.VERSION_PLANNING,
                    "progress": 38,
                    "revisions": revisions,
                }
            )
            result = result.model_copy(update={"run": run, "product_planning": planning})
            self.store.save(result)

            version_draft = self._generate_version_plan(
                result, requirements, provider, revisions
            )
            planning = planning.model_copy(update={"version_plan_draft": version_draft})
            result = result.model_copy(update={"product_planning": planning})
            self.store.save(result)
            version_plan, requirements = finalize_version_plan(
                version_draft,
                requirements,
                provider_name=provider.provider_name,
                model_name=provider.model_name,
            )
            version_validation = ValidationResult(
                id="VAL-VP-0001",
                analysis_run_id=analysis_run_id,
                target_type="VersionPlanDraft",
                target_id=version_draft.id,
                disposition=ArtifactValidationStatus.ACCEPTED,
            )
            planning = planning.model_copy(
                update={
                    "requirements": requirements,
                    "version_plan_draft": version_draft,
                    "version_plan_validation": version_validation,
                    "version_plan": version_plan,
                }
            )
            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.VERSION_PLANNING,
                    "current_stage": PipelineStage.PRD_GENERATION,
                    "progress": 58,
                }
            )
            result = result.model_copy(update={"run": run, "product_planning": planning})
            self.store.save(result)

            prd_draft = self._generate_structured_prd(
                result,
                eligible_findings,
                requirements,
                version_plan,
                provider,
                revisions,
            )
            planning = planning.model_copy(update={"structured_prd_draft": prd_draft})
            result = result.model_copy(update={"product_planning": planning})
            self.store.save(result)
            structured_prd = finalize_structured_prd(
                prd_draft, result, eligible_findings, requirements, version_plan
            )
            rendered_markdown = render_prd_markdown(
                structured_prd, result.run.resolved_output_language
            )
            prd_artifact = PRDArtifact(
                id="PRDA-0001",
                analysis_run_id=analysis_run_id,
                structured_prd=structured_prd,
                rendered_markdown=rendered_markdown,
                validation_result=ArtifactValidationStatus.REVISED,
                generated_by="runtime_llm_then_deterministic_renderer",
                model_provider=provider.provider_name,
                model_name=provider.model_name,
                generated_at=datetime.now(timezone.utc),
            )
            prd_validation = ValidationResult(
                id="VAL-PRD-0001",
                analysis_run_id=analysis_run_id,
                target_type="StructuredPRDDraft",
                target_id=prd_draft.id,
                disposition=ArtifactValidationStatus.REVISED,
                warnings=[
                    "Factual sections, counts, assumptions, and limitations were normalized from validated artifacts before deterministic Markdown rendering."
                ],
                revision_of=prd_draft.id,
            )
            planning = planning.model_copy(
                update={
                    "structured_prd_draft": prd_draft,
                    "prd_validation": prd_validation,
                    "prd_artifact": prd_artifact,
                }
            )
            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.PRD_GENERATION,
                    "current_stage": PipelineStage.TEST_CASE_GENERATION,
                    "progress": 76,
                }
            )
            result = result.model_copy(update={"run": run, "product_planning": planning})
            self.store.save(result)

            test_drafts = self._generate_test_cases(
                result, requirements, provider, revisions
            )
            planning = planning.model_copy(update={"test_case_drafts": test_drafts})
            result = result.model_copy(update={"product_planning": planning})
            self.store.save(result)
            test_cases, test_validations = finalize_test_cases(
                test_drafts,
                requirements,
                self.settings,
                provider_name=provider.provider_name,
                model_name=provider.model_name,
            )
            planning = planning.model_copy(
                update={
                    "test_case_drafts": test_drafts,
                    "test_case_validations": test_validations,
                    "test_cases": test_cases,
                }
            )
            run = run.model_copy(
                update={
                    "last_successful_stage": PipelineStage.TEST_CASE_GENERATION,
                    "current_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "progress": 93,
                }
            )
            result = result.model_copy(update={"run": run, "product_planning": planning})
            self.store.save(result)

            traceability = calculate_traceability(
                result, eligible_findings, requirements, test_cases
            )
            if traceability.hard_failures:
                raise ProductValidationError(
                    "TRACEABILITY_HARD_FAILURE",
                    " ".join(traceability.hard_failures),
                )
            planning_time = datetime.now(timezone.utc)
            planning = planning.model_copy(
                update={"traceability": traceability, "planning_time": planning_time}
            )
            warning_messages = list(result.run.warnings)
            if blocked_findings:
                warning_messages.append(
                    f"{len(blocked_findings)} non-eligible Findings were excluded from formal Requirement generation."
                )
            warning_messages.extend(traceability.warnings)
            completed_run = run.model_copy(
                update={
                    "status": (
                        AnalysisRunStatus.WARNING
                        if warning_messages
                        else AnalysisRunStatus.COMPLETED
                    ),
                    "current_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "last_successful_stage": PipelineStage.TRACEABILITY_VALIDATION,
                    "progress": 100,
                    "warnings": list(dict.fromkeys(warning_messages)),
                    "revisions": revisions,
                    "finished_at": planning_time,
                }
            )
            completed = result.model_copy(
                update={"run": completed_run, "product_planning": planning}
            )
            self.store.save(completed)
            return completed
        except (LLMProviderError, ProductValidationError, ValidationError) as error:
            latest = self.store.get(analysis_run_id) or result
            message = getattr(error, "message", str(error))
            failed_run = latest.run.model_copy(
                update={
                    "status": AnalysisRunStatus.FAILED,
                    "progress": min(latest.run.progress, 99),
                    "errors": [*latest.run.errors, message],
                    "error_code": getattr(error, "code", "PRODUCT_PLANNING_FAILED"),
                    "revisions": revisions,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            self.store.save(latest.model_copy(update={"run": failed_run}))
            if isinstance(error, ProductPlanningError):
                raise
            raise ProductPlanningError(
                getattr(error, "code", "PRODUCT_PLANNING_FAILED"),
                message,
                status_code=getattr(error, "status_code", 422),
            ) from error

    def _require_phase4_result(
        self, analysis_run_id: str
    ) -> tuple[IngestionResult, List[Finding], List[Finding]]:
        result = self.store.get(analysis_run_id)
        if result is None:
            raise ProductPlanningError(
                "RUN_NOT_FOUND", "Analysis run was not found.", status_code=404
            )
        try:
            eligible, blocked = validate_findings_for_planning(
                result,
                cross_run_owner=lambda review_id: self.store.find_review_owner(
                    review_id, excluding_analysis_run_id=analysis_run_id
                ),
            )
        except ProductValidationError as error:
            raise ProductPlanningError(
                error.code, error.message, status_code=error.status_code
            ) from error
        if not eligible:
            raise ProductPlanningError(
                "NO_ELIGIBLE_FINDINGS",
                "No SUPPORTED Finding is eligible for formal Requirement generation.",
                status_code=409,
            )
        return result, eligible, blocked

    def _generate_requirement_drafts(
        self,
        result: IngestionResult,
        findings: Sequence[Finding],
        provider: LLMProvider,
        revisions: List[str],
        generated_at: datetime,
    ) -> List[RequirementDraft]:
        drafts: List[RequirementDraft] = []
        for offset in range(0, len(findings), self.settings.product_finding_batch_size):
            batch = list(findings[offset : offset + self.settings.product_finding_batch_size])
            allowed_ids = {finding.id for finding in batch}
            output = self._call_with_retries(
                provider=provider,
                response_model=RequirementDraftOutput,
                schema_name="RequirementDraftOutput",
                system_prompt=load_prompt("requirement_generation.md"),
                user_prompt=self._requirement_prompt(result, batch),
                validator=lambda value, allowed_ids=allowed_ids: self._validate_requirement_output(
                    value, result.analysis_run_id, allowed_ids
                ),
                revisions=revisions,
                operation="Requirement generation",
            )
            for proposal in output.requirements:
                drafts.append(
                    RequirementDraft(
                        id=f"REQD-{len(drafts) + 1:04d}",
                        analysis_run_id=result.analysis_run_id,
                        generated_at=generated_at,
                        **proposal.model_dump(),
                    )
                )
        return drafts

    def _validate_requirement_grounding(
        self,
        result: IngestionResult,
        findings: Sequence[Finding],
        drafts: Sequence[RequirementDraft],
        provider: LLMProvider,
        revisions: List[str],
    ) -> List[RequirementGroundingDecision]:
        decisions: List[RequirementGroundingDecision] = []
        finding_by_id = {finding.id: finding for finding in findings}
        for offset in range(0, len(drafts), self.settings.product_finding_batch_size):
            batch = list(drafts[offset : offset + self.settings.product_finding_batch_size])
            output = self._call_with_retries(
                provider=provider,
                response_model=RequirementGroundingOutput,
                schema_name="RequirementGroundingOutput",
                system_prompt=load_prompt("requirement_grounding.md"),
                user_prompt=self._grounding_prompt(result, batch, finding_by_id),
                validator=lambda value, batch=batch: self._validate_grounding_output(
                    value, result.analysis_run_id, {draft.id for draft in batch}
                ),
                revisions=revisions,
                operation="Requirement grounding validation",
            )
            decisions.extend(output.decisions)
        return decisions

    def _generate_version_plan(
        self,
        result: IngestionResult,
        requirements: Sequence[Requirement],
        provider: LLMProvider,
        revisions: List[str],
    ) -> VersionPlanDraft:
        allowed_ids = {requirement.id for requirement in requirements}
        output = self._call_with_retries(
            provider=provider,
            response_model=VersionPlanDraftOutput,
            schema_name="VersionPlanDraftOutput",
            system_prompt=load_prompt("version_planning.md"),
            user_prompt=self._version_prompt(result, requirements),
            validator=lambda value: self._validate_version_output(
                value, result.analysis_run_id, allowed_ids
            ),
            revisions=revisions,
            operation="Version planning",
        )
        return VersionPlanDraft(
            id="VPD-0001",
            analysis_run_id=result.analysis_run_id,
            title=output.title,
            summary=output.summary,
            items=output.items,
            generated_at=datetime.now(timezone.utc),
        )

    def _generate_structured_prd(
        self,
        result: IngestionResult,
        findings: Sequence[Finding],
        requirements: Sequence[Requirement],
        version_plan: VersionPlan,
        provider: LLMProvider,
        revisions: List[str],
    ) -> StructuredPRDDraft:
        output = self._call_with_retries(
            provider=provider,
            response_model=StructuredPRDDraftOutput,
            schema_name="StructuredPRDDraftOutput",
            system_prompt=load_prompt("prd_generation.md"),
            user_prompt=self._prd_prompt(result, findings, requirements, version_plan),
            validator=lambda value: self._validate_prd_output(
                value,
                result.analysis_run_id,
                {finding.id for finding in findings},
                {requirement.id for requirement in requirements},
                {item.id for item in version_plan.items},
                version_plan.id,
            ),
            revisions=revisions,
            operation="Structured PRD generation",
        )
        return StructuredPRDDraft(
            id="PRDD-0001",
            analysis_run_id=result.analysis_run_id,
            generated_at=datetime.now(timezone.utc),
            **output.model_dump(exclude={"analysis_run_id"}),
        )

    def _generate_test_cases(
        self,
        result: IngestionResult,
        requirements: Sequence[Requirement],
        provider: LLMProvider,
        revisions: List[str],
    ) -> List[TestCaseDraft]:
        test_requirements = [
            requirement
            for requirement in requirements
            if requirement.validation_result
            in {ArtifactValidationStatus.ACCEPTED, ArtifactValidationStatus.REVISED}
        ]
        allowed_ids = {requirement.id for requirement in test_requirements}
        output = self._call_with_retries(
            provider=provider,
            response_model=TestCaseDraftOutput,
            schema_name="TestCaseDraftOutput",
            system_prompt=load_prompt("testcase_generation.md"),
            user_prompt=self._test_prompt(result, test_requirements),
            validator=lambda value: self._validate_test_output(
                value, result.analysis_run_id, allowed_ids
            ),
            revisions=revisions,
            operation="TestCase generation",
        )
        generated_at = datetime.now(timezone.utc)
        return [
            TestCaseDraft(
                id=f"TCD-{index:04d}",
                analysis_run_id=result.analysis_run_id,
                generated_at=generated_at,
                **proposal.model_dump(),
            )
            for index, proposal in enumerate(output.test_cases, start=1)
        ]

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
                    "instruction": "Correct the complete structured object using only the supplied allowlists.",
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
            except (LLMProviderError, ProductValidationError, ValidationError) as error:
                last_error = error
                revisions.append(
                    f"Attempt {attempt + 1} failed for {operation}: "
                    f"{getattr(error, 'code', type(error).__name__)}."
                )
                if isinstance(error, LLMProviderError) and not error.retryable:
                    break
                if attempt >= self.settings.llm_max_retries:
                    break
        if isinstance(last_error, (LLMProviderError, ProductValidationError)):
            raise last_error
        raise ProductValidationError(
            "INVALID_STRUCTURED_OUTPUT", f"Unable to complete {operation}."
        )

    def _validate_requirement_output(
        self,
        output: RequirementDraftOutput,
        run_id: str,
        allowed_finding_ids: set,
    ) -> None:
        if output.analysis_run_id != run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "Requirement output belongs to another run."
            )
        referenced = set()
        for proposal in output.requirements:
            if set(proposal.finding_ids) - allowed_finding_ids:
                raise ProductValidationError(
                    "INVALID_FINDING_ID", "Requirement output references a disallowed Finding."
                )
            if proposal.assumption:
                raise ProductValidationError(
                    "UNEXPECTED_ASSUMPTION",
                    "SUPPORTED Findings must not be converted into assumptions without cause.",
                )
            validate_acceptance_criteria(proposal.acceptance_criteria, self.settings)
            referenced.update(proposal.finding_ids)
        if referenced != allowed_finding_ids:
            raise ProductValidationError(
                "INCOMPLETE_FINDING_COVERAGE",
                "Requirement drafts must cover every allowed Finding.",
            )

    @staticmethod
    def _validate_grounding_output(
        output: RequirementGroundingOutput,
        run_id: str,
        allowed_draft_ids: set,
    ) -> None:
        if output.analysis_run_id != run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "Requirement validation belongs to another run."
            )
        ids = [decision.requirement_draft_id for decision in output.decisions]
        if len(ids) != len(set(ids)) or set(ids) != allowed_draft_ids:
            raise ProductValidationError(
                "INVALID_REQUIREMENT_VALIDATION",
                "Grounding decisions must exactly cover the current Requirement drafts.",
            )
        if any(decision.analysis_run_id != run_id for decision in output.decisions):
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "A grounding decision belongs to another run."
            )

    @staticmethod
    def _validate_version_output(
        output: VersionPlanDraftOutput,
        run_id: str,
        allowed_requirement_ids: set,
    ) -> None:
        if output.analysis_run_id != run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "VersionPlan output belongs to another run."
            )
        assigned = [item for plan_item in output.items for item in plan_item.requirement_ids]
        if len(assigned) != len(set(assigned)) or set(assigned) != allowed_requirement_ids:
            raise ProductValidationError(
                "INCOMPLETE_VERSION_PLAN",
                "VersionPlan must assign every allowed Requirement exactly once.",
            )

    @staticmethod
    def _validate_prd_output(
        output: StructuredPRDDraftOutput,
        run_id: str,
        allowed_findings: set,
        allowed_requirements: set,
        allowed_versions: set,
        version_plan_id: str,
    ) -> None:
        if output.analysis_run_id != run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "Structured PRD output belongs to another run."
            )
        if output.version_plan_id != version_plan_id:
            raise ProductValidationError(
                "INVALID_VERSION_REFERENCE", "Structured PRD references another VersionPlan."
            )
        sections = [
            *output.user_problems,
            *output.findings_summary,
            *output.requirements,
            *output.release_plan,
            *output.acceptance_criteria,
        ]
        for section in sections:
            if set(section.finding_ids) - allowed_findings:
                raise ProductValidationError(
                    "PRD_UNSUPPORTED_REFERENCE", "PRD references a disallowed Finding."
                )
            if set(section.requirement_ids) - allowed_requirements:
                raise ProductValidationError(
                    "PRD_REJECTED_REQUIREMENT_REFERENCE",
                    "PRD references a disallowed Requirement.",
                )
            if set(section.version_item_ids) - allowed_versions:
                raise ProductValidationError(
                    "INVALID_VERSION_REFERENCE", "PRD references a disallowed version item."
                )

    @staticmethod
    def _validate_test_output(
        output: TestCaseDraftOutput,
        run_id: str,
        allowed_requirement_ids: set,
    ) -> None:
        if output.analysis_run_id != run_id:
            raise ProductValidationError(
                "CROSS_RUN_REFERENCE", "TestCase output belongs to another run."
            )
        referenced = [test.requirement_id for test in output.test_cases]
        if any(requirement_id not in allowed_requirement_ids for requirement_id in referenced):
            raise ProductValidationError(
                "INVALID_REQUIREMENT_ID", "TestCase output references a disallowed Requirement."
            )
        if set(referenced) != allowed_requirement_ids:
            raise ProductValidationError(
                "INCOMPLETE_TEST_COVERAGE",
                "TestCase output must cover every allowed Requirement.",
            )
        if any(len(test.steps) < 2 for test in output.test_cases):
            raise ProductValidationError(
                "INVALID_TEST_CASE_QUALITY", "Every TestCase needs at least two steps."
            )

    @staticmethod
    def _finding_payload(finding: Finding) -> Dict[str, object]:
        return {
            "id": finding.id,
            "topic": finding.topic,
            "title": finding.title,
            "problem": finding.problem,
            "summary": finding.summary,
            "status": finding.status.value,
            "support_count": finding.support_count,
            "conflict_count": finding.conflict_count,
            "evidence_strength": finding.evidence_strength.value,
            "confidence": finding.confidence,
            "uncertainty": finding.uncertainty,
            "limitations": finding.limitations,
        }

    def _requirement_prompt(
        self, result: IngestionResult, findings: Sequence[Finding]
    ) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": result.run.resolved_output_language.value,
            "allowed_finding_ids": [finding.id for finding in findings],
            "validated_findings": [self._finding_payload(finding) for finding in findings],
            "json_schema": RequirementDraftOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _grounding_prompt(
        self,
        result: IngestionResult,
        drafts: Sequence[RequirementDraft],
        finding_by_id: Dict[str, Finding],
    ) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": result.run.resolved_output_language.value,
            "allowed_requirement_draft_ids": [draft.id for draft in drafts],
            "drafts": [draft.model_dump(mode="json") for draft in drafts],
            "validated_findings": [
                self._finding_payload(finding_by_id[finding_id])
                for finding_id in dict.fromkeys(
                    finding_id for draft in drafts for finding_id in draft.finding_ids
                )
            ],
            "json_schema": RequirementGroundingOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _version_prompt(
        result: IngestionResult, requirements: Sequence[Requirement]
    ) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": result.run.resolved_output_language.value,
            "allowed_requirement_ids": [requirement.id for requirement in requirements],
            "requirements": [
                {
                    "id": requirement.id,
                    "title": requirement.title,
                    "user_problem": requirement.user_problem,
                    "priority": requirement.final_priority.value,
                    "impact": requirement.impact.value,
                    "confidence": requirement.confidence,
                    "acceptance_criteria": requirement.acceptance_criteria,
                }
                for requirement in requirements
            ],
            "json_schema": VersionPlanDraftOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _prd_prompt(
        result: IngestionResult,
        findings: Sequence[Finding],
        requirements: Sequence[Requirement],
        version_plan: VersionPlan,
    ) -> str:
        limitations = list(
            dict.fromkeys(
                [
                    *result.provider.source_limitations,
                    *(limitation for finding in findings for limitation in finding.limitations),
                ]
            )
        )
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "analysis_goal": result.run.analysis_goal,
            "output_language": result.run.resolved_output_language.value,
            "allowed_finding_ids": [finding.id for finding in findings],
            "allowed_requirement_ids": [requirement.id for requirement in requirements],
            "allowed_version_item_ids": [item.id for item in version_plan.items],
            "version_plan_id": version_plan.id,
            "validated_findings": [ProductPlanningService._finding_payload(finding) for finding in findings],
            "validated_requirements": [requirement.model_dump(mode="json") for requirement in requirements],
            "validated_version_plan": version_plan.model_dump(mode="json"),
            "allowed_assumptions": [
                requirement.description for requirement in requirements if requirement.assumption
            ],
            "known_limitations": limitations,
            "json_schema": StructuredPRDDraftOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _test_prompt(
        result: IngestionResult, requirements: Sequence[Requirement]
    ) -> str:
        payload = {
            "analysis_run_id": result.analysis_run_id,
            "output_language": result.run.resolved_output_language.value,
            "allowed_requirement_ids": [requirement.id for requirement in requirements],
            "requirements": [
                {
                    "id": requirement.id,
                    "title": requirement.title,
                    "user_problem": requirement.user_problem,
                    "description": requirement.description,
                    "priority": requirement.final_priority.value,
                    "acceptance_criteria": requirement.acceptance_criteria,
                    "source_review_count": len(requirement.review_ids),
                }
                for requirement in requirements
                if requirement.validation_result
                in {ArtifactValidationStatus.ACCEPTED, ArtifactValidationStatus.REVISED}
            ],
            "json_schema": TestCaseDraftOutput.model_json_schema(),
        }
        return json.dumps(payload, ensure_ascii=False)


def product_planning_summary(
    planning: ProductPlanningResult,
) -> ProductPlanningSummary:
    return ProductPlanningSummary(
        analysis_run_id=planning.analysis_run_id,
        requirement_count=len(planning.requirements),
        rejected_requirement_count=sum(
            validation.disposition == ArtifactValidationStatus.REJECTED
            for validation in planning.requirement_validations
        ),
        version_count=len(planning.version_plan.items) if planning.version_plan else 0,
        prd_available=planning.prd_artifact is not None,
        test_case_count=len(planning.test_cases),
        model_provider=planning.model_provider,
        model_name=planning.model_name,
        planning_time=planning.planning_time,
        overall_traceability_coverage=(
            planning.traceability.overall_traceability_coverage
            if planning.traceability
            else None
        ),
    )
