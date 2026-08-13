from typing import Any, Dict, Optional


class IngestionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def with_run_id(self, run_id: str) -> "IngestionError":
        return IngestionError(
            self.code,
            self.message,
            status_code=self.status_code,
            details={**self.details, "analysis_run_id": run_id},
        )
