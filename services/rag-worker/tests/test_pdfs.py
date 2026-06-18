from pathlib import Path
import ipaddress
import socket
import tempfile
import time
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
from ringkas_worker import pdfs as pdf_module


PDF = b"%PDF-1.7\n" + (b"content" * 100)


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.requests = []
        self._handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    def close(self) -> None:
        pass


class SlowStream(httpx.SyncByteStream):
    def __iter__(self):
        yield PDF[:5]
        time.sleep(0.03)
        yield PDF[5:]


class TrackingStream(httpx.SyncByteStream):
    def __init__(self, *, fail: bool = False, delay_after_body: bool = False) -> None:
        self.fail = fail
        self.delay_after_body = delay_after_body
        self.closed = 0

    def __iter__(self):
        yield PDF
        if self.delay_after_body:
            time.sleep(0.03)
        if self.fail:
            raise httpx.ReadError("stream failure")

    def close(self) -> None:
        self.closed += 1


def production_downloader(tmp_path: Path, inner: httpx.BaseTransport, **kwargs) -> PdfDownloader:
    client = PdfDownloader(tmp_path, allowed_hosts={"example.test"}, **kwargs)
    client._client._transport._transport = inner
    return client


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


def test_from_settings_without_transport_constructs_validated_production_transport(tmp_path: Path) -> None:
    from ringkas_worker.config import WorkerSettings

    settings = WorkerSettings(
        DATABASE_URL="postgresql://ringkas:test@localhost:5432/ringkas",
        PDF_STORAGE_PATH=tmp_path,
        PDF_ALLOWED_HOSTS="example.test",
    )
    with PdfDownloader.from_settings(settings) as client:
        assert client._client._transport.__class__.__name__ == "_ValidatedAddressTransport"


class CustomTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("rejected transport must not receive a request")


@pytest.mark.parametrize("transport", [httpx.HTTPTransport(), CustomTransport()])
def test_unsupported_injected_transport_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: httpx.BaseTransport) -> None:
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


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1"])
def test_production_transport_rejects_unsafe_resolved_addresses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))])
    with PdfDownloader(tmp_path, allowed_hosts={"example.test"}) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())


def test_production_transport_sanitizes_resolution_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "dns-resolution-secret"
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(OSError(secret)))
    with PdfDownloader(tmp_path, allowed_hosts={"example.test"}) as client:
        with pytest.raises(PdfNetworkError) as error:
            client.download(publication())
    assert_sanitized(error.value, secret)


def test_production_transport_pins_dns_hostname_and_preserves_host_and_sni(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lookups = []
    inner = RecordingTransport(lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request))

    def resolve(host, port, **kwargs):
        lookups.append((host, port, kwargs))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with production_downloader(tmp_path, inner) as client:
        result = client.download(publication())

    assert result.checksum
    assert len(lookups) == 1
    assert inner.requests[0].url.host == "8.8.8.8"
    assert inner.requests[0].headers["host"] == "files.example.test"
    assert inner.requests[0].extensions["sni_hostname"] == "files.example.test"


def test_requestless_low_level_response_downloads_and_closes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = []

    class RequestlessTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.stream = TrackingStream()
            self.closed = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/pdf"}, stream=self.stream)

        def close(self) -> None:
            self.closed += 1

    def factory(**kwargs):
        transport = RequestlessTransport()
        created.append(transport)
        return transport

    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", factory)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    with PdfDownloader(tmp_path, allowed_hosts={"example.test"}) as client:
        result = client.download(publication())

    assert Path(result.local_pdf_path).read_bytes() == PDF
    assert created[0].stream.closed == 1
    assert created[0].closed == 1


def test_requestless_response_is_associated_by_outer_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class RequestlessTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/pdf"}, stream=TrackingStream())

        def close(self) -> None:
            pass

    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", lambda **kwargs: RequestlessTransport())
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    transport = pdf_module._ValidatedAddressTransport({"example.test"})
    with httpx.Client(transport=transport) as client:
        response = client.get("https://files.example.test/source.pdf")
        assert response.request.url.host == "files.example.test"


def test_requestless_stream_failure_closes_owned_resources_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created = []

    class RequestlessTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.stream = TrackingStream(fail=True)
            self.closed = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/pdf"}, stream=self.stream)

        def close(self) -> None:
            self.closed += 1

    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", lambda **kwargs: created.append(RequestlessTransport()) or created[-1])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    with PdfDownloader(tmp_path, allowed_hosts={"example.test"}) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())

    assert created[0].stream.closed == 1
    assert created[0].closed == 1
    assert not list(tmp_path.glob("*.part"))


def test_wrapper_construction_failure_closes_raw_response_and_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = TrackingStream()
    raw_response = httpx.Response(200, headers={"content-type": "application/pdf"}, stream=stream)

    class RequestlessTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return raw_response

        def close(self) -> None:
            self.closed += 1

    created = []
    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", lambda **kwargs: created.append(RequestlessTransport()) or created[-1])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    transport = pdf_module._ValidatedAddressTransport({"example.test"})
    monkeypatch.setattr(pdf_module.httpx, "Response", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("wrapper failure")))
    with pytest.raises(RuntimeError):
        transport.handle_request(httpx.Request("GET", "https://files.example.test/source.pdf"))

    assert stream.closed == 1
    assert created[0].closed == 1


def test_wrapper_failure_still_closes_transport_when_raw_response_close_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = TrackingStream()

    class CloseFailingResponse(httpx.Response):
        def close(self) -> None:
            super().close()
            raise RuntimeError("close failure")

    raw_response = CloseFailingResponse(200, headers={"content-type": "application/pdf"}, stream=stream)

    class RequestlessTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return raw_response

        def close(self) -> None:
            self.closed += 1

    created = []
    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", lambda **kwargs: created.append(RequestlessTransport()) or created[-1])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    transport = pdf_module._ValidatedAddressTransport({"example.test"})
    monkeypatch.setattr(pdf_module.httpx, "Response", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("wrapper failure")))

    with pytest.raises(RuntimeError, match="wrapper failure"):
        transport.handle_request(httpx.Request("GET", "https://files.example.test/source.pdf"))

    assert stream.closed == 1
    assert created[0].closed == 1


def test_production_transport_pins_ipv6_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inner = RecordingTransport(lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request))
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:4860:4860::8888", port or 443, 0, 0))],
    )
    with production_downloader(tmp_path, inner) as client:
        client.download(publication())
    assert inner.requests[0].url.host == "2001:4860:4860::8888"
    assert inner.requests[0].headers["host"] == "files.example.test"


@pytest.mark.parametrize("address", ["100.64.0.1", "fec0::1", "::ffff:100.64.0.1"])
def test_non_global_shared_or_site_local_addresses_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, family=family, sockaddr=sockaddr, **kwargs: [(family, socket.SOCK_STREAM, 6, "", sockaddr)])
    with production_downloader(tmp_path, RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request))) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())


def test_bracketed_public_ipv6_allow_list_literal_is_supported(tmp_path: Path) -> None:
    address = "2001:4860:4860::8888"
    inner = RecordingTransport(lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request))
    client = PdfDownloader(tmp_path, allowed_hosts={f"[{address}]"})
    client._client._transport._transport = inner
    try:
        client.download(publication(f"https://[{address}]/source.pdf"))
    finally:
        client.close()
    assert inner.requests[0].url.host == address
    assert inner.requests[0].headers["host"] == f"[{address}]"


@pytest.mark.parametrize("allowed", ["8.8.8.8", "100.64.0.1", "127.0.0.1"])
def test_ipv4_allow_list_accepts_only_global_literals(tmp_path: Path, allowed: str) -> None:
    if allowed == "8.8.8.8":
        PdfDownloader(tmp_path, allowed_hosts={allowed}).close()
    else:
        with pytest.raises(PdfUrlError):
            PdfDownloader(tmp_path, allowed_hosts={allowed})


def test_literal_ip_allow_list_requires_exact_match(tmp_path: Path) -> None:
    assert pdf_module._is_allowed_host("8.8.8.8", {"8.8.8.8"})
    assert not pdf_module._is_allowed_host("example.8.8.8.8", {"8.8.8.8"})


def test_hostname_allow_list_keeps_subdomain_boundary_matching(tmp_path: Path) -> None:
    with PdfDownloader(tmp_path, allowed_hosts={"example.test"}, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request))) as client:
        client.download(publication("https://cdn.example.test/source.pdf"))


@pytest.mark.parametrize("allowed", ["2001:4860:4860::8888", "[2001:4860:4860::8888", "[not-ipv6]"])
def test_ambiguous_or_malformed_ipv6_allow_list_is_rejected(tmp_path: Path, allowed: str) -> None:
    with pytest.raises(PdfUrlError):
        PdfDownloader(tmp_path, allowed_hosts={allowed})


def test_multiple_public_addresses_are_tried_without_resolving_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    inner = RecordingTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("unreachable", request=request))
        if request.url.host == "8.8.8.8"
        else httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: (calls.append(host), [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port or 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port or 443)),
        ])[1],
    )
    with production_downloader(tmp_path, inner) as client:
        client.download(publication())
    assert calls == ["files.example.test"]
    assert [request.url.host for request in inner.requests] == ["8.8.8.8", "1.1.1.1"]


def test_unsafe_secondary_address_is_never_attempted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inner = RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request))
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.1", 443)),
        ],
    )
    with production_downloader(tmp_path, inner) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())
    assert not inner.requests


def test_same_ip_hosts_use_independent_owned_transports(monkeypatch: pytest.MonkeyPatch) -> None:
    created = []

    class ClosableTransport(RecordingTransport):
        def __init__(self):
            super().__init__(lambda request: httpx.Response(200, content=PDF, request=request))
            self.closed = False

        def close(self):
            self.closed = True

    def factory(**kwargs):
        transport = ClosableTransport()
        created.append(transport)
        return transport

    monkeypatch.setattr(pdf_module.httpx, "HTTPTransport", factory)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    transport = pdf_module._ValidatedAddressTransport({"a.example.test", "b.example.test"})
    for host in ("a.example.test", "b.example.test"):
        response = transport.handle_request(httpx.Request("GET", f"https://{host}/file.pdf"))
        response.close()
    assert len(created) == 2
    assert created[0] is not created[1]
    assert all(item.closed for item in created)


def test_pinned_request_preserves_safe_headers_and_strips_sensitive_headers() -> None:
    request = httpx.Request(
        "GET",
        "https://a.example.test/file.pdf",
        headers={
            "Accept": "application/pdf",
            "User-Agent": "ringkas-test",
            "Authorization": "Bearer secret",
            "Proxy-Authorization": "Basic secret",
            "Cookie": "session=secret",
            "X-Api-Key": "secret",
        },
    )
    pinned = pdf_module._pinned_request(request, request.url, request.url.host, ipaddress.ip_address("8.8.8.8"))
    assert pinned.headers["accept"] == "application/pdf"
    assert pinned.headers["user-agent"] == "ringkas-test"
    for name in ("authorization", "proxy-authorization", "cookie", "x-api-key"):
        assert name not in pinned.headers


def test_compose_propagates_pdf_total_timeout() -> None:
    compose = Path(__file__).parents[3] / "infra" / "docker-compose.yml"
    assert "PDF_TOTAL_TIMEOUT_SECONDS" in compose.read_text(encoding="utf-8")


def test_redirect_resolves_and_pins_each_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lookups = []
    inner = RecordingTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://cdn.example.test/final.pdf"},
            request=request,
        )
        if request.url.path == "/source.pdf"
        else httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)
    )

    def resolve(host, port, **kwargs):
        lookups.append(host)
        address = "8.8.8.8" if host == "files.example.test" else "1.1.1.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with production_downloader(tmp_path, inner) as client:
        client.download(publication())
    assert lookups == ["files.example.test", "cdn.example.test"]
    assert [request.url.host for request in inner.requests] == ["8.8.8.8", "1.1.1.1"]
    assert [request.headers["host"] for request in inner.requests] == ["files.example.test", "cdn.example.test"]


def test_redirect_dns_change_to_private_is_rejected_before_second_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    inner = RecordingTransport(lambda request: httpx.Response(302, headers={"location": "https://cdn.example.test/final.pdf"}, request=request))

    def resolve(host, port, **kwargs):
        calls.append(host)
        address = "8.8.8.8" if len(calls) == 1 else "169.254.169.254"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with production_downloader(tmp_path, inner) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())
    assert calls == ["files.example.test", "cdn.example.test"]
    assert len(inner.requests) == 1
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("value", [True, False, 0, -1, float("nan"), float("inf"), float("-inf"), "bad"])
def test_pdf_timeouts_require_finite_positive_values(tmp_path: Path, value: object) -> None:
    for name in ("connect_timeout_seconds", "read_timeout_seconds", "total_timeout_seconds"):
        kwargs = {name: value}
        with pytest.raises(PdfValidationError):
            PdfDownloader(tmp_path, allowed_hosts={"example.test"}, **kwargs)


def test_empty_and_malformed_dns_answers_fail_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for answer in ([], [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ())], [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 443))]):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, answer=answer, **kwargs: answer)
        with production_downloader(tmp_path, RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request))) as client:
            with pytest.raises(PdfNetworkError):
                client.download(publication())


def test_dns_that_returns_after_deadline_fails_with_typed_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_resolve(*args, **kwargs):
        time.sleep(0.03)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", slow_resolve)
    with production_downloader(tmp_path, RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request)), total_timeout_seconds=0.01) as client:
        with pytest.raises(PdfTimeoutError):
            client.download(publication())


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1", "192.0.2.1", "0.0.0.0", "::1", "::"])
def test_all_unsafe_resolved_addresses_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, family=family, sockaddr=sockaddr, **kwargs: [(family, socket.SOCK_STREAM, 6, "", sockaddr)])
    with production_downloader(tmp_path, RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request))) as client:
        with pytest.raises(PdfNetworkError):
            client.download(publication())


def test_unsafe_ip_literal_is_rejected_before_dns_or_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("literal must not resolve")))
    inner = RecordingTransport(lambda request: httpx.Response(200, content=PDF, request=request))
    with production_downloader(tmp_path, inner) as client:
        with pytest.raises(PdfUrlError):
            client.download(publication("https://127.0.0.1/private.pdf"))
    assert not inner.requests


def test_slow_drip_cannot_exceed_total_deadline(tmp_path: Path) -> None:
    inner = RecordingTransport(lambda request: httpx.Response(200, stream=SlowStream(), headers={"content-type": "application/pdf"}, request=request))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
        with production_downloader(tmp_path, inner, total_timeout_seconds=0.01) as client:
            with pytest.raises(PdfTimeoutError):
                client.download(publication())
    assert not list(tmp_path.glob("*.part"))


def test_deadline_after_final_chunk_before_eof_is_typed_timeout(tmp_path: Path) -> None:
    inner = RecordingTransport(lambda request: httpx.Response(200, stream=TrackingStream(delay_after_body=True), headers={"content-type": "application/pdf"}, request=request))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
        with production_downloader(tmp_path, inner, total_timeout_seconds=0.01) as client:
            with pytest.raises(PdfTimeoutError):
                client.download(publication())


def test_malformed_redirect_location_is_typed_and_sanitized(tmp_path: Path) -> None:
    secret = "https://user:secret@[bad"
    with downloader(tmp_path, lambda request: httpx.Response(302, headers={"location": secret}, request=request)) as client:
        with pytest.raises(PdfUrlError) as error:
            client.download(publication())
    assert_sanitized(error.value, "secret")


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
