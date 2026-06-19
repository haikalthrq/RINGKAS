from pathlib import Path
import socket
import tempfile
import traceback

import httpx
import pytest

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.pdfs import (
    PdfDownloader,
    PdfCanonicalCorruptionError,
    PdfNetworkError,
    PdfResponseError,
    PdfStorageError,
    PdfTimeoutError,
    PdfTransportError,
    PdfUrlError,
    PdfValidationError,
)


PDF = b"%PDF-1.7\n" + (b"content" * 100)


def publication(url: str = "https://files.example.test/source.pdf") -> PublicationMetadata:
    return PublicationMetadata(
        title="Test publication", publication_year=2025, region="DKI Jakarta",
        region_level="province", source_page_url="https://bps.example.test/source",
        pdf_url=url,
    )


def downloader(tmp_path: Path, handler, **kwargs) -> PdfDownloader:
    return PdfDownloader(tmp_path, allowed_hosts={"example.test"}, transport=httpx.MockTransport(handler), **kwargs)


def assert_sanitized(error: BaseException, secret: str) -> None:
    rendered = "\n".join((str(error), repr(error), "".join(traceback.format_exception(error))))
    assert secret not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


def test_streamed_pdf_is_finalized_as_checksum_path(tmp_path: Path) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        result = client.download(publication())
    assert result.checksum == __import__("hashlib").sha256(PDF).hexdigest()
    assert Path(result.local_pdf_path).read_bytes() == PDF
    assert result.local_pdf_path == str(tmp_path / f"{result.checksum}.pdf")
    assert not list(tmp_path.glob("*.part"))


def test_duplicate_checksum_reuses_verified_canonical_without_second_file(tmp_path: Path) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        first = client.download(publication())
        second = client.download(publication("https://files.example.test/other-name.pdf"))
    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_corrupt_canonical_is_rejected_without_overwrite_or_duplicate(tmp_path: Path) -> None:
    checksum = __import__("hashlib").sha256(PDF).hexdigest()
    canonical = tmp_path / f"{checksum}.pdf"
    canonical.write_bytes(b"%PDF-corrupt")
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        with pytest.raises(PdfCanonicalCorruptionError) as error:
            client.download(publication())
    assert canonical.read_bytes() == b"%PDF-corrupt"
    assert not list(tmp_path.glob("*.part"))
    assert_sanitized(error.value, str(tmp_path))


def test_no_transport_fails_closed_without_creating_http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_host = "example.test"

    def fail_client(*args, **kwargs):
        raise AssertionError("live HTTP client must not be constructed")

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS must not be called")))

    monkeypatch.setattr("ringkas_worker.pdfs.httpx.Client", fail_client)
    with pytest.raises(PdfTransportError) as error:
        PdfDownloader(tmp_path, allowed_hosts={allowed_host})
    assert_sanitized(error.value, allowed_host)


class CustomTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("rejected transport must not receive a request")


@pytest.mark.parametrize("transport", [httpx.HTTPTransport(), CustomTransport()])
def test_only_mock_transport_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: httpx.BaseTransport) -> None:
    monkeypatch.setattr("ringkas_worker.pdfs.httpx.Client", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("client must not be constructed")))
    with pytest.raises(PdfTransportError) as error:
        PdfDownloader(tmp_path, allowed_hosts={"example.test"}, transport=transport)  # type: ignore[arg-type]
    assert_sanitized(error.value, "transport-detail")
    assert "HTTPTransport" not in repr(error.value)
    assert "CustomTransport" not in repr(error.value)


def test_zero_redirects_disables_redirects(tmp_path: Path) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(302, headers={"location": "/final.pdf"}, request=request), max_redirects=0) as client:
        with pytest.raises(PdfResponseError):
            client.download(publication())


@pytest.mark.parametrize("response", [httpx.Response(404), httpx.Response(500)])
def test_non_success_response_is_rejected_and_temp_cleaned(tmp_path: Path, response: httpx.Response) -> None:
    with downloader(tmp_path, lambda request: response) as client:
        with pytest.raises(PdfResponseError):
            client.download(publication())
    assert not list(tmp_path.glob("*.part"))


def test_redirect_is_validated_and_followed_manually(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/source.pdf":
            return httpx.Response(302, headers={"location": "/final.pdf"}, request=request)
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)

    with downloader(tmp_path, handler) as client:
        assert client.download(publication()).checksum


def test_unsafe_redirect_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"}, request=request)

    with downloader(tmp_path, handler) as client:
        with pytest.raises(PdfUrlError):
            client.download(publication())
    assert not list(tmp_path.glob("*.part"))


def test_oversized_response_is_stopped(tmp_path: Path) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request), max_size_bytes=10) as client:
        with pytest.raises(PdfValidationError):
            client.download(publication())
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("content_type", ["text/html", "application/json"])
def test_disallowed_content_type_is_rejected(tmp_path: Path, content_type: str) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": content_type}, request=request)) as client:
        with pytest.raises(PdfValidationError):
            client.download(publication())


def test_invalid_signature_is_rejected(tmp_path: Path) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=b"not pdf", headers={"content-type": "application/pdf"}, request=request)) as client:
        with pytest.raises(PdfValidationError):
            client.download(publication())
    assert not list(tmp_path.glob("*.pdf"))


def test_timeout_and_network_errors_are_typed(tmp_path: Path) -> None:
    secret = "request-header-secret"

    def timeout(request: httpx.Request) -> httpx.Response:
        request.headers["X-Secret"] = secret
        raise httpx.ReadTimeout(f"timeout {secret}", request=request)

    def network(request: httpx.Request) -> httpx.Response:
        request.headers["X-Secret"] = secret
        raise httpx.ConnectError(f"network {secret}", request=request)

    with downloader(tmp_path, timeout) as client:
        with pytest.raises(PdfTimeoutError) as error:
            client.download(publication())
    assert_sanitized(error.value, secret)
    with downloader(tmp_path, network) as client:
        with pytest.raises(PdfNetworkError) as error:
            client.download(publication())
    assert_sanitized(error.value, secret)


def test_mkdir_failure_is_typed_and_does_not_expose_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_mkdir(*args, **kwargs):
        raise OSError(f"secret path={tmp_path}")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, request=request)) as client:
        with pytest.raises(PdfStorageError) as error:
            client.download(publication())
    assert_sanitized(error.value, str(tmp_path))


def test_temporary_file_creation_failure_is_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda **kwargs: (_ for _ in ()).throw(OSError(f"path={tmp_path}")))
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, request=request)) as client:
        with pytest.raises(PdfStorageError) as error:
            client.download(publication())
    assert_sanitized(error.value, str(tmp_path))


class FailingTemporaryFile:
    name = "temporary-part"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, chunk):
        raise OSError("write path secret")

    def flush(self):
        pass

    def fileno(self):
        return 1


class FlushFailingTemporaryFile(FailingTemporaryFile):
    def write(self, chunk):
        return len(chunk)

    def flush(self):
        raise OSError("flush path secret")


@pytest.mark.parametrize("failure", ["write", "flush", "fsync", "replace"])
def test_filesystem_failures_are_typed_and_cleanup_is_attempted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    cleanup = []
    if failure == "write":
        monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda **kwargs: FailingTemporaryFile())
    elif failure == "flush":
        monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda **kwargs: FlushFailingTemporaryFile())
    elif failure == "fsync":
        monkeypatch.setattr("ringkas_worker.pdfs.os.fsync", lambda fd: (_ for _ in ()).throw(OSError("fsync path secret")))
    else:
        monkeypatch.setattr("ringkas_worker.pdfs.os.replace", lambda source, target: (_ for _ in ()).throw(OSError("replace path secret")))
    original_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *args, **kwargs: (cleanup.append(self), original_unlink(self, *args, **kwargs))[1])
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        with pytest.raises(PdfStorageError) as error:
            client.download(publication())
    assert cleanup
    assert_sanitized(error.value, "secret")
    assert_sanitized(error.value, str(tmp_path))


def test_canonical_read_failure_is_typed_and_temp_is_cleaned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checksum = __import__("hashlib").sha256(PDF).hexdigest()
    (tmp_path / f"{checksum}.pdf").write_bytes(PDF)
    original_open = Path.open

    def fail_open(self, *args, **kwargs):
        if self.name == f"{checksum}.pdf":
            raise OSError(f"canonical path={tmp_path}")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        with pytest.raises(PdfStorageError) as error:
            client.download(publication())
    assert not list(tmp_path.glob("*.part"))
    assert_sanitized(error.value, str(tmp_path))


def test_cleanup_failure_does_not_replace_primary_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cleanup_attempted = []

    def fail_cleanup(self, *args, **kwargs):
        cleanup_attempted.append(True)
        raise OSError(f"cleanup path={tmp_path}")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda **kwargs: FailingTemporaryFile())
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)) as client:
        with pytest.raises(PdfStorageError) as error:
            client.download(publication())
    assert cleanup_attempted
    assert_sanitized(error.value, str(tmp_path))
@pytest.mark.parametrize("url", ["https://other.test/a.pdf"])
def test_url_safety_rejects_unsafe_urls(tmp_path: Path, url: str) -> None:
    with downloader(tmp_path, lambda request: httpx.Response(200, content=PDF, request=request)) as client:
        with pytest.raises(PdfUrlError):
            client.download(publication(url))
