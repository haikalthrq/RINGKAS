import pytest
import traceback
from pydantic import ValidationError

from ringkas_worker.config import WorkerSettings


def valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://worker:secret@localhost/ringkas")


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("INGESTION_POLL_INTERVAL_SECONDS", "15")
    settings = WorkerSettings()
    assert settings.ingestion_poll_interval_seconds == 15
    assert settings.database_url.get_secret_value().startswith("postgresql://")


@pytest.mark.parametrize(
    "name,value",
    [
        ("INGESTION_POLL_INTERVAL_SECONDS", "0"),
        ("DATABASE_CONNECT_TIMEOUT_SECONDS", "0"),
        ("DATABASE_STATEMENT_TIMEOUT_MS", "0"),
        ("CHUNK_SIZE_MIN", "0"),
        ("CHUNK_OVERLAP_PERCENT", "100"),
    ],
)
def test_invalid_ranges_fail_safely(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        WorkerSettings()


def test_ocr_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("OCR_ENABLED", "true")
    with pytest.raises(ValidationError, match="OCR_ENABLED=true"):
        WorkerSettings()


@pytest.mark.parametrize("value", ["", "sqlite:///tmp/ringkas.db", "mysql://localhost/ringkas"])
def test_database_url_must_be_postgres_without_echoing_secret(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValidationError) as error:
        WorkerSettings()
    assert "secret" not in str(error.value).lower()


def test_qdrant_url_and_pdf_path_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("QDRANT_URL", "ftp://qdrant:6333")
    with pytest.raises(ValidationError):
        WorkerSettings()


def test_secret_values_are_masked_in_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("QDRANT_API_KEY", "qdrant-secret")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-secret")
    settings = WorkerSettings()
    assert "secret" not in repr(settings).lower()

    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("PDF_STORAGE_PATH", "relative/pdfs")
    with pytest.raises(ValidationError):
        WorkerSettings()


def test_bps_base_url_is_optional_but_validated_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("BPS_BASE_URL", "https://api.example.invalid/")
    monkeypatch.setenv("BPS_PUBLICATIONS_PATH", "publications")
    settings = WorkerSettings()
    assert settings.bps_base_url == "https://api.example.invalid"
    assert settings.bps_publications_path == "publications"

    monkeypatch.setenv("BPS_BASE_URL", "ftp://api.example.invalid")
    with pytest.raises(ValidationError):
        WorkerSettings()


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://api.example.invalid",
        "https://",
        "https://user:password@example.invalid",
        "https://example.invalid?token=secret-token",
        "https://example.invalid/#secret-fragment",
    ],
)
def test_bps_base_url_rejects_unsafe_values_without_echoing_secrets(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("BPS_BASE_URL", base_url)
    with pytest.raises(ValidationError) as error:
        WorkerSettings()

    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert "password" not in rendered
    assert "secret-token" not in rendered


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example.invalid/publications",
        "//other.example.invalid/publications",
        "publications?token=secret-token",
        "publications#secret-fragment",
        " ",
        "../private",
        "nested/../private",
    ],
)
def test_bps_publications_path_rejects_unsafe_values(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("BPS_PUBLICATIONS_PATH", path)
    with pytest.raises(ValidationError):
        WorkerSettings()


@pytest.mark.parametrize(
    "name,value",
    [
        ("PDF_MAX_SIZE_BYTES", "0"),
        ("PDF_CONNECT_TIMEOUT_SECONDS", "0"),
        ("PDF_READ_TIMEOUT_SECONDS", "-1"),
        ("PDF_MAX_REDIRECTS", "-1"),
    ],
)
def test_pdf_limits_are_validated(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        WorkerSettings()


@pytest.mark.parametrize(
    "value",
    [
        "https://example.test/files",
        "example.test/path",
        "example.test?token=secret",
        "example.test#fragment",
        "*.example.test",
        "user:password@example.test",
        "https://example.test",
    ],
)
def test_pdf_allowed_hosts_reject_url_like_or_wildcard_entries(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("PDF_ALLOWED_HOSTS", value)
    with pytest.raises(ValidationError):
        WorkerSettings()


def test_pdf_allowed_hosts_normalize_exact_hosts_and_subdomain_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_environment(monkeypatch)
    monkeypatch.setenv("PDF_ALLOWED_HOSTS", " BPS.Example.TEST., files.example.test ")
    settings = WorkerSettings()
    assert settings.pdf_allowed_hosts == "bps.example.test,files.example.test"
