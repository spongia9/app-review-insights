from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.providers.base import ReviewCandidate
from app.providers.errors import IngestionError


FIELD_ALIASES = {
    "id": ("review_id", "source_review_id"),
    "text": ("review", "review_text", "content", "body", "comment"),
    "title": ("review_title",),
    "rating": ("score", "stars", "star_rating"),
    "version": ("app_version", "review_version"),
    "author": ("user", "username", "reviewer"),
    "date": ("created_at", "review_date"),
    "language": ("lang", "locale"),
    "app_id": ("application_id",),
    "storefront": ("country", "country_code", "store"),
}

CANONICAL_FIELDS = tuple(FIELD_ALIASES)


def resolve_headers(headers: List[str]) -> Dict[str, str]:
    normalized_headers: Dict[str, str] = {}
    for header in headers:
        normalized = header.strip().lower()
        if not normalized:
            continue
        if normalized in normalized_headers:
            raise IngestionError(
                "INVALID_IMPORT_SCHEMA",
                f"Duplicate column name after normalization: {normalized}.",
                status_code=422,
            )
        normalized_headers[normalized] = header

    resolved: Dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        canonical_header = normalized_headers.get(canonical)
        matched_aliases = [
            normalized_headers[alias] for alias in aliases if alias in normalized_headers
        ]

        if canonical_header is not None:
            resolved[canonical] = canonical_header
            continue
        if len(matched_aliases) > 1:
            raise IngestionError(
                "AMBIGUOUS_IMPORT_SCHEMA",
                f"Multiple aliases map to '{canonical}': {', '.join(matched_aliases)}.",
                status_code=422,
            )
        if matched_aliases:
            resolved[canonical] = matched_aliases[0]

    if "text" not in resolved:
        raise IngestionError(
            "INVALID_IMPORT_SCHEMA",
            "A 'text' column or one documented text alias is required.",
            status_code=422,
        )
    return resolved


def candidate_from_mapping(
    row: Mapping[str, Any],
    *,
    source: str,
    resolved_headers: Optional[Dict[str, str]] = None,
) -> ReviewCandidate:
    headers = resolved_headers or resolve_headers([str(key) for key in row.keys()])
    canonical: Dict[str, Any] = {
        field: row.get(source_field) for field, source_field in headers.items()
    }
    return ReviewCandidate(
        source=source,
        raw_data=dict(row),
        source_review_id=canonical.get("id"),
        app_id=canonical.get("app_id"),
        author=canonical.get("author"),
        rating=canonical.get("rating"),
        title=canonical.get("title"),
        text=canonical.get("text"),
        version=canonical.get("version"),
        language=canonical.get("language"),
        created_at=canonical.get("date"),
        storefront=canonical.get("storefront"),
    )


def require_upload_within_limit(data: bytes, max_upload_bytes: int) -> None:
    if len(data) > max_upload_bytes:
        raise IngestionError(
            "FILE_TOO_LARGE",
            f"The uploaded file exceeds the {max_upload_bytes}-byte limit.",
            status_code=413,
            details={"maximum_file_size_bytes": max_upload_bytes},
        )


def require_record_limit(record_count: int, max_review_rows: int) -> None:
    if record_count > max_review_rows:
        raise IngestionError(
            "TOO_MANY_REVIEWS",
            f"The file contains more than {max_review_rows} review records.",
            status_code=413,
            details={"maximum_review_rows": max_review_rows},
        )


def decode_utf8(data: bytes, source_label: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise IngestionError(
            f"INVALID_{source_label.upper()}",
            f"{source_label.upper()} uploads must use UTF-8 or UTF-8 with BOM.",
            status_code=422,
            details={"byte_offset": error.start},
        ) from error
