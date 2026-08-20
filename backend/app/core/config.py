from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    service_name: str = "app-review-insights-api"
    api_prefix: str = "/api"
    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_url: str = "http://localhost:5173"
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    sqlite_database_path: Path = PROJECT_ROOT / "backend" / "data" / "app-review-insights.db"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_review_rows: int = Field(default=10_000, ge=1)
    app_store_max_pages: int = Field(default=5, ge=1, le=10)
    app_store_request_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[SecretStr] = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_review_batch_size: int = Field(default=25, ge=1, le=200)
    llm_consolidation_group_size: int = Field(default=4, ge=2, le=10)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_request_timeout_seconds: float = Field(default=180.0, gt=0, le=300)
    llm_max_output_tokens: int = Field(default=32768, ge=4096, le=32768)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_thinking_enabled: bool = False
    llm_trust_environment_proxy: bool = False

    evidence_batch_size: int = Field(default=20, ge=1, le=100)
    evidence_conflict_pool_max_reviews: int = Field(default=60, ge=1, le=500)
    evidence_semantic_relevance_threshold: float = Field(default=0.55, ge=0, le=1)
    evidence_min_relevant_reviews: int = Field(default=2, ge=1, le=100)
    evidence_supported_min_count: int = Field(default=4, ge=1, le=100)
    evidence_supported_min_ratio: float = Field(default=0.70, ge=0, le=1)
    evidence_conflict_min_count: int = Field(default=2, ge=1, le=100)
    evidence_conflict_ratio_threshold: float = Field(default=0.30, ge=0, le=1)
    evidence_high_strength_min_count: int = Field(default=8, ge=1, le=500)
    evidence_high_strength_min_confidence: float = Field(default=0.80, ge=0, le=1)
    evidence_medium_strength_min_confidence: float = Field(default=0.55, ge=0, le=1)
    evidence_confidence_sample_cap: int = Field(default=10, ge=1, le=100)
    evidence_weak_confidence_cap: float = Field(default=0.69, ge=0, le=1)
    evidence_conflicted_confidence_cap: float = Field(default=0.74, ge=0, le=1)
    evidence_insufficient_confidence_cap: float = Field(default=0.45, ge=0, le=1)
    evidence_unsupported_confidence_cap: float = Field(default=0.20, ge=0, le=1)

    product_finding_batch_size: int = Field(default=8, ge=1, le=25)
    product_acceptance_criteria_min_count: int = Field(default=2, ge=1, le=10)
    product_acceptance_criterion_min_chars: int = Field(default=8, ge=4, le=100)
    product_p0_min_support_count: int = Field(default=20, ge=1, le=1000)
    product_p0_min_confidence: float = Field(default=0.85, ge=0, le=1)
    product_p1_min_support_count: int = Field(default=8, ge=1, le=1000)
    product_p1_min_confidence: float = Field(default=0.70, ge=0, le=1)

    @field_validator("sqlite_database_path", mode="after")
    @classmethod
    def resolve_database_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def allowed_cors_origins(self) -> List[str]:
        return list(dict.fromkeys([*self.cors_origins, self.frontend_url]))


@lru_cache
def get_settings() -> Settings:
    return Settings()
