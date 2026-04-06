"""Configuration loading from .env and environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Looker connection settings loaded from .env or environment."""

    # Required
    looker_base_url: str = Field(
        ..., description="Looker instance URL (e.g., https://mycompany.cloud.looker.com)"
    )
    looker_client_id: str = Field(..., description="Looker API client ID")
    looker_client_secret: str = Field(..., description="Looker API client secret")

    # Optional
    looker_port: int = Field(443, description="Looker API port")
    looker_api_version: str = Field("4.0", description="Looker API version")
    looker_verify_ssl: bool = Field(True, description="Verify SSL certificates")
    looker_timeout: int = Field(120, description="HTTP request timeout in seconds")

    # Extraction
    concurrency: int = Field(10, description="Max concurrent API calls")
    output_format: str = Field("jsonl", description="Default output format")
    output_path: str = Field("output.jsonl", description="Default output path")

    # BigQuery (optional)
    bq_project: Optional[str] = Field(None, description="BigQuery project ID")
    bq_dataset: Optional[str] = Field(None, description="BigQuery dataset name")
    bq_table: Optional[str] = Field(None, description="BigQuery table name")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def api_url(self) -> str:
        """Construct the full API base URL (trailing slash for httpx resolution)."""
        base = self.looker_base_url.rstrip("/")
        if self.looker_port != 443:
            base = f"{base}:{self.looker_port}"
        return f"{base}/api/{self.looker_api_version}/"

    @property
    def swagger_url(self) -> str:
        """Construct the Swagger spec URL."""
        base = self.looker_base_url.rstrip("/")
        if self.looker_port != 443:
            base = f"{base}:{self.looker_port}"
        return f"{base}/api/{self.looker_api_version}/swagger.json"


def load_settings(env_file: Path | str = ".env") -> Settings:
    """Load settings from the given .env file path."""
    return Settings(_env_file=str(env_file))
