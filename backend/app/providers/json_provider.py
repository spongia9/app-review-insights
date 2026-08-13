import json
from datetime import datetime, timezone
from typing import Any, List

from app.models.ingestion import RejectedReview
from app.providers.base import ProviderBatch, ReviewCandidate, ReviewProvider
from app.providers.errors import IngestionError
from app.providers.import_contract import (
    candidate_from_mapping,
    decode_utf8,
    require_record_limit,
    require_upload_within_limit,
)


class JSONProvider(ReviewProvider):
    source = "json_upload"

    def __init__(self, data: bytes, *, max_upload_bytes: int, max_review_rows: int) -> None:
        self.data = data
        self.max_upload_bytes = max_upload_bytes
        self.max_review_rows = max_review_rows

    def load(self) -> ProviderBatch:
        require_upload_within_limit(self.data, self.max_upload_bytes)
        text = decode_utf8(self.data, "json")
        try:
            document: Any = json.loads(text)
        except json.JSONDecodeError as error:
            raise IngestionError(
                "INVALID_JSON",
                f"The JSON file is malformed at line {error.lineno}, column {error.colno}.",
                status_code=422,
            ) from error

        if isinstance(document, list):
            rows = document
        elif isinstance(document, dict) and set(document.keys()) == {"reviews"} and isinstance(
            document["reviews"], list
        ):
            rows = document["reviews"]
        else:
            raise IngestionError(
                "INVALID_JSON",
                "JSON must be an array of review objects or an object containing only a 'reviews' array.",
                status_code=422,
            )

        require_record_limit(len(rows), self.max_review_rows)
        candidates: List[ReviewCandidate] = []
        rejected_rows: List[RejectedReview] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                rejected_rows.append(
                    RejectedReview(
                        row_number=index,
                        code="INVALID_ROW",
                        message="Each JSON review must be an object.",
                    )
                )
                continue
            try:
                candidates.append(candidate_from_mapping(row, source=self.source))
            except IngestionError as error:
                rejected_rows.append(
                    RejectedReview(
                        row_number=index,
                        code=error.code,
                        message=error.message,
                    )
                )

        return ProviderBatch(
            source=self.source,
            collection_time=datetime.now(timezone.utc),
            candidates=candidates,
            raw_review_count=len(rows),
            source_limitations=[
                "Uploaded JSON data is user-supplied and is not verified as live App Store data."
            ],
            rejected_rows=rejected_rows,
        )
