import argparse
import random
import sys
from pathlib import Path
from typing import List


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.llm import create_llm_provider  # noqa: E402
from app.services.evidence import EvidenceValidationService  # noqa: E402
from app.storage import RunStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real Phase 4 evidence-validation smoke test without printing secrets."
    )
    parser.add_argument("analysis_run_id")
    parser.add_argument(
        "--candidate-id",
        action="append",
        dest="candidate_ids",
        required=True,
        help="Finding Candidate ID to validate; repeat for multiple candidates.",
    )
    parser.add_argument("--spot-check-count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260814)
    return parser.parse_args()


def excerpt(value: str, limit: int = 220) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[:limit - 1]}…"


def main() -> None:
    args = parse_args()
    settings = Settings()
    store = RunStore(settings.sqlite_database_path)
    store.initialize()
    before = store.get(args.analysis_run_id)
    if before is None:
        raise SystemExit("Analysis run was not found.")
    provider = create_llm_provider(settings)
    print(f"provider_class={type(provider).__name__}")
    print(f"provider={provider.provider_name}")
    print(f"model={provider.model_name}")
    print(f"source={before.provider.source}")
    print(f"cached={before.run.source_type.value in {'cached', 'demo'}}")
    print(f"selected_candidates={len(args.candidate_ids)}")

    service = EvidenceValidationService(
        settings,
        store,
        provider_factory=lambda _: provider,
    )
    service.queue(args.analysis_run_id, candidate_ids=args.candidate_ids)
    completed = service.validate(args.analysis_run_id, candidate_ids=args.candidate_ids)
    evidence = completed.evidence_validation
    if evidence is None:
        raise SystemExit("Evidence validation did not produce a result.")

    current_review_ids = {review.id for review in completed.reviews}
    for finding in evidence.findings:
        assert set(finding.supporting_review_ids).issubset(current_review_ids)
        assert set(finding.conflicting_review_ids).issubset(current_review_ids)
        assert not set(finding.supporting_review_ids).intersection(finding.conflicting_review_ids)

    print(f"run_status={completed.run.status.value}")
    print(f"current_stage={completed.run.current_stage.value}")
    print(f"last_successful_stage={completed.run.last_successful_stage.value if completed.run.last_successful_stage else None}")
    print(f"validated_candidates={evidence.validated_candidate_count}/{evidence.total_candidate_count}")
    print(f"validated_unique_reviews={evidence.validated_review_count}")
    print(f"validation_batches={evidence.batch_count}")
    print(f"hallucinated_review_ids=0")
    for finding in evidence.findings:
        print(
            "finding="
            f"{finding.validation_metadata.finding_candidate_id}|{finding.title}|"
            f"{finding.status.value}|support={finding.support_count}|"
            f"conflict={finding.conflict_count}|confidence={finding.confidence:.4f}|"
            f"strength={finding.evidence_strength.value}"
        )
        print(f"uncertainty={finding.uncertainty}")

    review_by_id = {review.id: review for review in completed.reviews}
    audit_by_candidate = {audit.finding_candidate_id: audit for audit in evidence.audits}
    sample_size = min(args.spot_check_count, len(evidence.findings))
    selected = random.Random(args.seed).sample(evidence.findings, sample_size)
    print(f"spot_check_count={len(selected)}")
    for finding in selected:
        audit = audit_by_candidate[finding.validation_metadata.finding_candidate_id]
        print(f"spot_check={finding.title}|status={finding.status.value}")
        for stance, review_ids in (
            ("SUPPORTS", finding.supporting_review_ids[:3]),
            ("CONFLICTS", finding.conflicting_review_ids[:3]),
        ):
            for review_id in review_ids:
                judgment = next(item for item in audit.judgments if item.review_id == review_id)
                print(
                    f"evidence={stance}|{review_id}|"
                    f"review={excerpt(review_by_id[review_id].text)}|"
                    f"reason={excerpt(judgment.reason)}"
                )


if __name__ == "__main__":
    main()
