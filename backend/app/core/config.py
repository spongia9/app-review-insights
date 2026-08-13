from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field
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

    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None

    @property
    def allowed_cors_origins(self) -> List[str]:
        return list(dict.fromkeys([*self.cors_origins, self.frontend_url]))


@lru_cache
def get_settings() -> Settings:
    return Settings()
