import json
from pathlib import Path

from pydantic import ValidationError

from app.models import IngestionResult
from app.storage import RunStore


CACHED_RESULTS_DIR = Path(__file__).resolve().parents[3] / "cached_results"
WORKOUT_DEMO_PATH = CACHED_RESULTS_DIR / "workout_demo.json"


class CachedDemoError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_workout_demo(store: RunStore) -> IngestionResult:
    """Validate and persist the packaged demo without changing its provenance."""

    try:
        payload = json.loads(WORKOUT_DEMO_PATH.read_text(encoding="utf-8"))
        result = IngestionResult.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise CachedDemoError(
            "CACHED_DEMO_UNAVAILABLE",
            "The packaged Workout cached demo is missing or invalid.",
        ) from error
    if result.cached_demo is None or not result.cached_demo.CACHED_DEMO:
        raise CachedDemoError(
            "CACHED_DEMO_UNAVAILABLE",
            "The packaged result is not marked as a cached demo.",
        )
    if not all(
        (
            result.semantic_analysis,
            result.evidence_validation,
            result.product_planning,
            result.final_traceability,
        )
    ):
        raise CachedDemoError(
            "CACHED_DEMO_UNAVAILABLE",
            "The packaged Workout cached demo is incomplete.",
        )
    store.save(result)
    return result
