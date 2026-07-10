import ipaddress
import math
from pathlib import Path, PurePosixPath

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ringkas_worker.bps.urls import normalize_publications_path, validate_base_url


def _validate_pdf_allowed_hosts(value: str) -> str:
    from urllib.parse import urlsplit

    entries = [entry.strip() for entry in value.split(",") if entry.strip()]
    for entry in entries:
        candidate = entry.lower().rstrip(".")
        if not candidate or "*" in candidate:
            raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host")
        if candidate.startswith("["):
            if not candidate.endswith("]"):
                raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host")
            try:
                address = ipaddress.ip_address(candidate[1:-1])
            except ValueError:
                raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host") from None
            if not isinstance(address, ipaddress.IPv6Address) or not address.is_global:
                raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host")
            continue
        if ":" in candidate:
            raise ValueError("PDF_ALLOWED_HOSTS IPv6 literals must be bracketed")
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            address = None
        if address is not None:
            if not isinstance(address, ipaddress.IPv4Address) or not address.is_global:
                raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host")
            continue
        try:
            parsed = urlsplit("//" + candidate)
            if parsed.hostname != candidate or parsed.username is not None or parsed.password is not None:
                raise ValueError
            if parsed.path or parsed.query or parsed.fragment or parsed.port is not None:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("PDF_ALLOWED_HOSTS contains an invalid host") from None
    return ",".join(entry.lower().rstrip(".") for entry in entries)


class WorkerSettings(BaseSettings):
    """Environment-backed settings required by the polling worker."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    database_url: SecretStr = Field(validation_alias="DATABASE_URL", repr=False)
    qdrant_url: AnyHttpUrl = Field(default="http://qdrant:6333", validation_alias="QDRANT_URL")
    qdrant_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="QDRANT_API_KEY", repr=False)
    pdf_storage_path: Path = Field(default=Path("/data/ringkas/pdfs"), validation_alias="PDF_STORAGE_PATH")
    pdf_max_size_bytes: int = Field(default=50 * 1024 * 1024, validation_alias="PDF_MAX_SIZE_BYTES")
    pdf_connect_timeout_seconds: float = Field(default=10.0, validation_alias="PDF_CONNECT_TIMEOUT_SECONDS")
    pdf_read_timeout_seconds: float = Field(default=60.0, validation_alias="PDF_READ_TIMEOUT_SECONDS")
    pdf_total_timeout_seconds: float = Field(default=300.0, validation_alias="PDF_TOTAL_TIMEOUT_SECONDS")
    pdf_max_redirects: int = Field(default=5, validation_alias="PDF_MAX_REDIRECTS")
    pdf_allowed_hosts: str = Field(default="", validation_alias="PDF_ALLOWED_HOSTS")
    bps_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="BPS_API_KEY", repr=False)
    bps_base_url: str = Field(default="https://webapi.bps.go.id/v1/api/list", validation_alias="BPS_BASE_URL")
    bps_publications_path: str = Field(default="", validation_alias="BPS_PUBLICATIONS_PATH")
    bps_publication_keyword: str = Field(default="", validation_alias="BPS_PUBLICATION_KEYWORD")
    ingestion_poll_interval_seconds: int = Field(default=10, validation_alias="INGESTION_POLL_INTERVAL_SECONDS")
    database_connect_timeout_seconds: int = Field(default=10, validation_alias="DATABASE_CONNECT_TIMEOUT_SECONDS")
    database_statement_timeout_ms: int = Field(default=30_000, validation_alias="DATABASE_STATEMENT_TIMEOUT_MS")
    chunk_size_min: int = Field(default=500, validation_alias="CHUNK_SIZE_MIN")
    chunk_size_max: int = Field(default=800, validation_alias="CHUNK_SIZE_MAX")
    chunk_overlap_percent: int = Field(default=20, validation_alias="CHUNK_OVERLAP_PERCENT")
    ocr_enabled: bool = Field(default=False, validation_alias="OCR_ENABLED")

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: SecretStr) -> SecretStr:
        database_url = value.get_secret_value()
        if not database_url.strip():
            raise ValueError("DATABASE_URL is required for worker polling")
        if not database_url.lower().startswith(("postgres://", "postgresql://")):
            raise ValueError("DATABASE_URL must use the postgres or postgresql scheme")
        return value

    @field_validator("bps_base_url")
    @classmethod
    def bps_base_url_must_be_http_when_configured(cls, value: str) -> str:
        if not value.strip():
            return value
        try:
            return str(validate_base_url(value)).rstrip("/")
        except Exception:
            raise ValueError("BPS_BASE_URL must be a safe absolute HTTP or HTTPS URL") from None

    @field_validator("bps_publications_path")
    @classmethod
    def bps_publications_path_must_be_relative(cls, value: str) -> str:
        try:
            return normalize_publications_path(value)
        except Exception:
            raise ValueError("BPS_PUBLICATIONS_PATH must be a safe relative path") from None

    @field_validator("bps_publication_keyword")
    @classmethod
    def bps_publication_keyword_must_be_bounded(cls, value: str) -> str:
        if len(value) > 200:
            raise ValueError("BPS_PUBLICATION_KEYWORD must not exceed 200 characters")
        return value.strip()

    @field_validator("pdf_storage_path")
    @classmethod
    def pdf_path_must_be_absolute(cls, value: Path) -> Path:
        # The worker runs in Linux containers but configuration tests may run on Windows.
        if not value.is_absolute() and not PurePosixPath(value.as_posix()).is_absolute():
            raise ValueError("PDF_STORAGE_PATH must be an absolute path")
        return value

    @field_validator("pdf_allowed_hosts")
    @classmethod
    def pdf_hosts_are_safe_boundaries(cls, value: str) -> str:
        return _validate_pdf_allowed_hosts(value)

    @field_validator(
        "ingestion_poll_interval_seconds",
        "database_connect_timeout_seconds",
        "database_statement_timeout_ms",
        "chunk_size_min",
        "chunk_size_max",
        "pdf_max_size_bytes",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("poll interval, database timeouts, and chunk sizes must be positive")
        return value

    @field_validator("pdf_max_redirects")
    @classmethod
    def non_negative_redirect_limit(cls, value: int) -> int:
        if value < 0:
            raise ValueError("PDF_MAX_REDIRECTS must be zero or greater")
        return value

    @field_validator("pdf_connect_timeout_seconds", "pdf_read_timeout_seconds", "pdf_total_timeout_seconds")
    @classmethod
    def positive_pdf_timeout(cls, value: float) -> float:
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("PDF timeouts must be positive")
        return value

    @field_validator("chunk_size_max")
    @classmethod
    def max_chunk_must_cover_minimum(cls, value: int, info) -> int:
        minimum = info.data.get("chunk_size_min")
        if minimum is not None and minimum > value:
            raise ValueError("CHUNK_SIZE_MIN must be less than or equal to CHUNK_SIZE_MAX")
        return value

    @field_validator("chunk_overlap_percent")
    @classmethod
    def safe_overlap(cls, value: int) -> int:
        if not 0 <= value < 100:
            raise ValueError("CHUNK_OVERLAP_PERCENT must be between 0 and 99")
        return value

    @field_validator("ocr_enabled")
    @classmethod
    def ocr_is_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("OCR_ENABLED=true is not supported in the MVP worker")
        return value
