import pytest
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
