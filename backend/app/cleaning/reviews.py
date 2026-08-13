import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import ValidationError

from app.models import CleaningStatistics, Review
from app.models.ingestion import RejectedReview
from app.providers.base import ProviderBatch, ReviewCandidate
from app.providers.errors import IngestionError


WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized or None


def normalize_rating(value: Any) -> Optional[float]:
    if value is None or normalize_text(value) is None:
        return None
    try:
        rating = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError("rating must be numeric") from error
    if rating < 1 or rating > 5:
        raise ValueError("rating must be between 1 and 5")
    return rating


def normalize_datetime(value: Any) -> Optional[datetime]:
    text = normalize_text(value)
    if text is None:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError("date must be ISO 8601") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_language(value: Any) -> Optional[str]:
    text = normalize_text(value)
    if text is None:
        return None
    text = text.replace("_", "-")
    parts = text.split("-")
    return "-".join([parts[0].lower(), *[part.upper() for part in parts[1:]]])


def _fingerprint(candidate: Dict[str, Any]) -> str:
    material = "\x1f".join(
        [
            (candidate.get("title") or "").casefold(),
            candidate["text"].casefold(),
            "" if candidate.get("rating") is None else str(candidate["rating"]),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def clean_reviews(
    batch: ProviderBatch,
    *,
    analysis_run_id: str,
) -> Tuple[List[Review], CleaningStatistics, List[RejectedReview]]:
    reviews: List[Review] = []
    rejected = list(batch.rejected_rows)
    empty_count = 0
    invalid_count = len(batch.rejected_rows)
    duplicate_count = 0
    seen_source_ids: Set[Tuple[str, str]] = set()
    seen_fingerprints: Set[str] = set()

    for index, candidate in enumerate(batch.candidates, start=1):
        try:
            normalized = _normalize_candidate(candidate, batch)
        except ValueError as error:
            code = "EMPTY_REVIEW" if "text" in str(error) else "INVALID_ROW"
            if code == "EMPTY_REVIEW":
                empty_count += 1
            else:
                invalid_count += 1
            rejected.append(
                RejectedReview(row_number=index, code=code, message=str(error))
            )
            continue

        source_review_id = normalized.get("source_review_id")
        if source_review_id:
            source_key = (batch.source, source_review_id)
            if source_key in seen_source_ids:
                duplicate_count += 1
                continue
            seen_source_ids.add(source_key)
        else:
            fingerprint = _fingerprint(normalized)
            if fingerprint in seen_fingerprints:
                duplicate_count += 1
                continue
            seen_fingerprints.add(fingerprint)

        normalized["id"] = f"R{len(reviews) + 1:06d}"
        normalized["analysis_run_id"] = analysis_run_id
        try:
            reviews.append(Review.model_validate(normalized))
        except ValidationError as error:
            invalid_count += 1
            rejected.append(
                RejectedReview(
                    row_number=index,
                    code="INVALID_ROW",
                    message=error.errors()[0]["msg"],
                )
            )

    if not reviews:
        raise IngestionError(
            "NO_VALID_REVIEWS",
            "No valid reviews remained after validation and cleaning.",
            status_code=422,
            details={"analysis_run_id": analysis_run_id},
        )

    raw_count = batch.raw_review_count
    statistics = CleaningStatistics(
        analysis_run_id=analysis_run_id,
        raw_review_count=raw_count,
        clean_review_count=len(reviews),
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        empty_count=empty_count,
        retention_rate=len(reviews) / raw_count if raw_count else 0,
    )
    return reviews, statistics, rejected


def _normalize_candidate(candidate: ReviewCandidate, batch: ProviderBatch) -> Dict[str, Any]:
    text = normalize_text(candidate.text)
    if text is None:
        raise ValueError("review text must not be empty")

    return {
        "source": batch.source,
        "source_review_id": normalize_text(candidate.source_review_id),
        "app_id": normalize_text(candidate.app_id) or batch.app_id,
        "author": normalize_text(candidate.author),
        "rating": normalize_rating(candidate.rating),
        "title": normalize_text(candidate.title),
        "text": text,
        "version": normalize_text(candidate.version),
        "language": normalize_language(candidate.language),
        "created_at": normalize_datetime(candidate.created_at),
        "storefront": normalize_text(candidate.storefront) or batch.storefront,
        "raw_data": candidate.raw_data,
    }
