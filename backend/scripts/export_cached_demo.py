"""Export a validated persisted run as the distributable offline demo."""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.models import CachedDemoMetadata  # noqa: E402
from app.storage import RunStore  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "cached_results" / "workout_demo.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_run_id")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    settings = Settings()
    result = RunStore(settings.sqlite_database_path).get(args.analysis_run_id)
    if result is None:
        raise SystemExit(f"Run not found: {args.analysis_run_id}")
    if not all(
        (
            result.semantic_analysis,
            result.evidence_validation,
            result.product_planning,
            result.final_traceability,
        )
    ):
        raise SystemExit("The selected run does not contain a complete final pipeline.")
    semantic = result.semantic_analysis
    if semantic.analysis_time is None:
        raise SystemExit("The selected run has no semantic analysis timestamp.")

    cached = result.model_copy(
        update={
            "provider": result.provider.model_copy(
                update={
                    "source": f"cached_demo:{result.provider.source}",
                    "is_live_collection": False,
                    "source_limitations": [
                        *result.provider.source_limitations,
                        "This packaged artifact is a cached demonstration result, not a live collection.",
                    ],
                }
            ),
            "cached_demo": CachedDemoMetadata(
                source=result.provider.source,
                collection_time=result.provider.collection_time,
                model_provider=semantic.model_provider,
                model_name=semantic.model_name,
                analysis_time=semantic.analysis_time,
            ),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(cached.model_dump_json(), encoding="utf-8")
    print(f"Exported cached demo to {args.output}")


if __name__ == "__main__":
    main()
