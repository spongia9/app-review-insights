import csv
import io
from datetime import datetime, timezone
from typing import List

from app.models.ingestion import RejectedReview
from app.providers.base import ProviderBatch, ReviewCandidate, ReviewProvider
from app.providers.errors import IngestionError
from app.providers.import_contract import (
    candidate_from_mapping,
    decode_utf8,
    require_record_limit,
    require_upload_within_limit,
    resolve_headers,
)


class CSVProvider(ReviewProvider):
    source = "csv_upload"

    def __init__(self, data: bytes, *, max_upload_bytes: int, max_review_rows: int) -> None:
        self.data = data
        self.max_upload_bytes = max_upload_bytes
        self.max_review_rows = max_review_rows

    def load(self) -> ProviderBatch:
        require_upload_within_limit(self.data, self.max_upload_bytes)
        text = decode_utf8(self.data, "csv")

        try:
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            if reader.fieldnames is None:
                raise IngestionError(
                    "INVALID_CSV",
                    "The CSV file must include a header row.",
                    status_code=422,
                )
            resolved_headers = resolve_headers(reader.fieldnames)
            candidates: List[ReviewCandidate] = []
            rejected_rows: List[RejectedReview] = []
            raw_count = 0
            for row_number, row in enumerate(reader, start=2):
                raw_count += 1
                require_record_limit(raw_count, self.max_review_rows)
                if None in row:
                    rejected_rows.append(
                        RejectedReview(
                            row_number=row_number,
                            code="INVALID_ROW",
                            message="The row has more values than the header defines.",
                        )
                    )
                    continue
                candidates.append(
                    candidate_from_mapping(
                        row,
                        source=self.source,
                        resolved_headers=resolved_headers,
                    )
                )
        except csv.Error as error:
            raise IngestionError(
                "INVALID_CSV",
                f"The CSV file is malformed: {error}.",
                status_code=422,
            ) from error

        return ProviderBatch(
            source=self.source,
            collection_time=datetime.now(timezone.utc),
            candidates=candidates,
            raw_review_count=raw_count,
            source_limitations=[
                "Uploaded CSV data is user-supplied and is not verified as live App Store data."
            ],
            rejected_rows=rejected_rows,
        )
