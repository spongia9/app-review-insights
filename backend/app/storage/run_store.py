import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Optional

from app.models import IngestionResult


class RunStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = Lock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, result: IngestionResult) -> None:
        payload = result.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_runs (id, source_type, status, result_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    source_type = excluded.source_type,
                    status = excluded.status,
                    result_json = excluded.result_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.analysis_run_id,
                    result.run.source_type.value,
                    result.run.status.value,
                    payload,
                ),
            )

    def get(self, analysis_run_id: str) -> Optional[IngestionResult]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analysis_runs WHERE id = ?",
                (analysis_run_id,),
            ).fetchone()
        if row is None:
            return None
        return IngestionResult.model_validate(json.loads(row[0]))

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.database_path), timeout=5)
