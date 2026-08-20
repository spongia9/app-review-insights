import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.llm import create_llm_provider  # noqa: E402
from app.models import ArtifactValidationStatus, FindingEvidenceStatus  # noqa: E402
from app.services.product_planning import ProductPlanningService  # noqa: E402
from app.storage import RunStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real Phase 5 product-planning smoke test without printing secrets."
    )
    parser.add_argument("analysis_run_id")
    parser.add_argument("--review-count", type=int, default=5)
    parser.add_argument("--prd-output", type=Path)
    return parser.parse_args()


def compact(value: str, limit: int = 260) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def main() -> None:
    args = parse_args()
    settings = Settings()
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    before = store.get(args.analysis_run_id)
    if before is None:
        raise SystemExit("Analysis run was not found.")
    if before.evidence_validation is None:
        raise SystemExit("Phase 4 evidence validation is required.")

    provider = create_llm_provider(settings)
    if provider.provider_name.startswith("mock"):
        raise SystemExit("Real smoke test refuses a mock provider.")

    print(f"provider_class={type(provider).__name__}")
    print(f"provider={provider.provider_name}")
    print(f"model={provider.model_name}")
    print(f"source={before.provider.source}")
    print(f"cached={before.run.source_type.value in {'cached', 'demo'}}")
    print(f"output_language={before.run.resolved_output_language.value}")

    service = ProductPlanningService(settings, store, provider_factory=lambda _: provider)
    service.queue(args.analysis_run_id)
    completed = service.generate(args.analysis_run_id)
    planning = completed.product_planning
    if planning is None or planning.prd_artifact is None or planning.version_plan is None:
        raise SystemExit("Product planning did not produce all required artifacts.")

    finding_by_id = {
        finding.id: finding for finding in completed.evidence_validation.findings
    }
    review_ids = {review.id for review in completed.reviews}
    requirement_by_id = {requirement.id: requirement for requirement in planning.requirements}

    for requirement in planning.requirements:
        source_findings = [finding_by_id[finding_id] for finding_id in requirement.finding_ids]
        assert all(finding.status is FindingEvidenceStatus.SUPPORTED for finding in source_findings)
        inherited = {
            review_id
            for finding in source_findings
            for review_id in finding.supporting_review_ids
        }
        assert set(requirement.review_ids) == inherited
        assert set(requirement.review_ids).issubset(review_ids)
        assert requirement.validation_result in {
            ArtifactValidationStatus.ACCEPTED,
            ArtifactValidationStatus.REVISED,
        }

    for test_case in planning.test_cases:
        requirement = requirement_by_id[test_case.requirement_id]
        assert set(test_case.source_review_ids) == set(requirement.review_ids)
        assert len(test_case.steps) >= 2

    assert planning.traceability is not None
    assert not planning.traceability.hard_failures
    assert planning.traceability.overall_traceability_coverage == 1

    prd_path = args.prd_output or (
        BACKEND_ROOT / "data" / "artifacts" / args.analysis_run_id / "PRD.md"
    )
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    prd_path.write_text(planning.prd_artifact.rendered_markdown, encoding="utf-8")

    print(f"run_status={completed.run.status.value}")
    print(f"last_successful_stage={completed.run.last_successful_stage.value if completed.run.last_successful_stage else None}")
    print(f"requirements={len(planning.requirements)}")
    print(f"versions={len(planning.version_plan.items)}")
    print(f"test_cases={len(planning.test_cases)}")
    print(f"traceability={planning.traceability.overall_traceability_coverage:.2f}")
    print(f"hallucinated_review_ids=0")
    print(f"unsupported_formal_requirements=0")
    print(f"prd_path={prd_path.resolve()}")
    print(f"prd_characters={len(planning.prd_artifact.rendered_markdown)}")

    for index, requirement in enumerate(planning.requirements[: args.review_count], start=1):
        source_titles = [finding_by_id[item].title for item in requirement.finding_ids]
        print(f"requirement_review_candidate_{index}=REQUIRES_HUMAN_JUDGMENT")
        print(f"source_findings_{index}={' | '.join(source_titles)}")
        print(f"requirement_{index}={requirement.title}")
        print(f"acceptance_{index}={' | '.join(requirement.acceptance_criteria)}")
        print(f"evidence_ids_{index}={' '.join(requirement.review_ids)}")

    for index, test_case in enumerate(planning.test_cases[: args.review_count], start=1):
        requirement = requirement_by_id[test_case.requirement_id]
        print(f"test_review_candidate_{index}=REQUIRES_HUMAN_JUDGMENT")
        print(f"test_requirement_{index}={requirement.title}")
        print(f"test_{index}={test_case.title}")
        print(f"expected_{index}={compact(test_case.expected_result)}")


if __name__ == "__main__":
    main()
