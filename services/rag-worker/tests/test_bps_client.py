import traceback

import httpx
import pytest

from ringkas_worker.bps.client import BpsClient
from ringkas_worker.bps.errors import (
    BpsAuthenticationError,
    BpsConfigurationError,
    BpsInvalidJsonError,
    BpsInvalidMetadataError,
    BpsNetworkError,
    BpsResponseShapeError,
    BpsTimeoutError,
    BpsUpstreamError,
)
from ringkas_worker.bps.mapper import map_publications
from ringkas_worker.config import WorkerSettings


OFFICIAL_PAYLOAD = {
    "status": "OK",
    "data": [
        {"page": 1, "pages": 1, "per_page": 10, "count": 1, "total": 1},
        [{
                "pub_id": "3100-2025-001",
                "title": "Profil Kemiskinan Provinsi DKI Jakarta 2025",
                "issn": "1234-5678",
                "sch_date": "2025-06-01",
                "rl_date": "2025-06-18",
                "updt_date": None,
                "cover": "https://webapi.bps.go.id/cover/3100-2025-001",
                "pdf": "https://webapi.bps.go.id/publication/3100-2025-001.pdf?download=1",
                "size": "1 MB",
            }],
    ]
}


def test_official_data_one_fixture_maps_publication_metadata() -> None:
    publication = map_publications(OFFICIAL_PAYLOAD)[0]

    assert publication.external_id == "3100-2025-001"
    assert publication.title == "Profil Kemiskinan Provinsi DKI Jakarta 2025"
    assert publication.publication_year == 2025
    assert str(publication.release_date) == "2025-06-18"
    assert publication.region == "DKI Jakarta"
    assert publication.region_level == "province"
    assert publication.language == "ind"
    assert publication.publication_number == "1234-5678"
    assert publication.pdf_url is not None
    assert str(publication.pdf_url).startswith("https://webapi.bps.go.id/")
    assert str(publication.source_page_url) == "https://webapi.bps.go.id/publication/3100-2025-001.pdf"


@pytest.mark.parametrize(
    "item",
    [
        {"title": "Title", "rl_date": "2025-01-01", "pdf": "https://example.invalid/source.pdf"},
        {"pub_id": "1", "rl_date": "2025-01-01", "pdf": "https://example.invalid/source.pdf"},
        {"pub_id": "1", "title": "Title", "rl_date": "invalid", "pdf": "https://example.invalid/source.pdf"},
    ],
)
def test_invalid_metadata_is_rejected(item: dict[str, object]) -> None:
    with pytest.raises(BpsInvalidMetadataError):
        map_publications({"data": [{}, [item]]})


@pytest.mark.parametrize(
    "source_page_url",
    [
        "https://user:password@example.invalid/publication",
    ],
)
def test_invalid_metadata_error_does_not_retain_upstream_url(source_page_url: str) -> None:
    with pytest.raises(BpsInvalidMetadataError) as error:
        map_publications(
            {
                "data": [{}, [
                        {
                            "pub_id": "1",
                            "title": "Title",
                            "rl_date": "2025-01-01",
                            "pdf": source_page_url,
                        }
                ]]
            }
        )

    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert source_page_url not in rendered
    assert error.value.__cause__ is None


def test_optional_metadata_can_be_absent() -> None:
    publication = map_publications(
        {"data": [{}, [{"pub_id": 1, "title": "Title", "rl_date": "2025-01-01", "pdf": None}]]}
    )[0]
    assert publication.external_id == "1"
    assert publication.pdf_url is None
    assert str(publication.source_page_url) == "https://webapi.bps.go.id/v1/api/list"


def test_invalid_response_shape_is_rejected() -> None:
    with pytest.raises(BpsResponseShapeError):
        map_publications({"items": []})


def test_client_builds_configured_path_and_uses_mock_transport() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OFFICIAL_PAYLOAD, request=request)

    with BpsClient(
        "https://placeholder.invalid/api/",
        "publications",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.fetch_publications()

    assert str(seen[0].url) == "https://placeholder.invalid/api/publications?model=publication&domain=3100&lang=ind"


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://example.invalid",
        "https://",
        "https://user:password@example.invalid",
        "https://example.invalid?token=secret-token",
        "https://example.invalid/#secret-fragment",
    ],
)
def test_unsafe_base_url_is_rejected_without_echoing_value(base_url: str) -> None:
    with pytest.raises(BpsConfigurationError) as error:
        BpsClient(base_url)
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert "password" not in rendered
    assert "secret-token" not in rendered
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "publications_path",
    [
        "https://other.invalid/publications",
        "//other.invalid/publications",
        "publications?token=secret-token",
        "publications#secret-fragment",
        " ",
        "../private",
        "nested/../private",
        "%2e%2e/private",
        "%2E%2E/private",
        "%252e%252e/private",
        "nested/%2e%2e/private",
        "%2e%2e%2fprivate",
        "%252e%252e%252fprivate",
    ],
)
def test_unsafe_publications_path_is_rejected(publications_path: str) -> None:
    with pytest.raises(BpsConfigurationError):
        BpsClient("https://placeholder.invalid", publications_path)


def test_publications_path_is_normalized_and_joined_structurally() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OFFICIAL_PAYLOAD, request=request)

    with BpsClient(
        "https://placeholder.invalid/api/",
        "/nested/publications/",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.fetch_publications()

    assert str(seen[0].url) == "https://placeholder.invalid/api/nested/publications?model=publication&domain=3100&lang=ind"


def test_from_settings_places_bps_key_in_query_parameter_only() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OFFICIAL_PAYLOAD, request=request)

    settings = WorkerSettings(
        DATABASE_URL="postgresql://worker:test@localhost/ringkas",
        BPS_API_KEY="test-bps-key",
        BPS_BASE_URL="https://webapi.bps.go.id/v1/api/list",
    )
    with BpsClient.from_settings(settings, transport=httpx.MockTransport(handler)) as client:
        client.fetch_publications()

    request = seen[0]
    assert request.url.params["key"] == "test-bps-key"
    assert request.url.params["model"] == "publication"
    assert request.url.params["domain"] == "3100"
    assert request.url.params["lang"] == "ind"
    assert "Authorization" not in request.headers


def test_configured_publication_keyword_is_forwarded_without_replacing_contract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OFFICIAL_PAYLOAD, request=request)

    settings = WorkerSettings(
        DATABASE_URL="postgresql://worker:test@localhost/ringkas",
        BPS_API_KEY="test-bps-key",
        BPS_BASE_URL="https://webapi.bps.go.id/v1/api/list",
        BPS_PUBLICATION_KEYWORD="Profil Kemiskinan Provinsi DKI Jakarta 2025",
    )
    with BpsClient.from_settings(settings, transport=httpx.MockTransport(handler)) as client:
        client.fetch_publications()

    assert seen[0].url.params["keyword"] == "Profil Kemiskinan Provinsi DKI Jakarta 2025"
    assert seen[0].url.params["model"] == "publication"
    assert seen[0].url.params["domain"] == "3100"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(503), BpsUpstreamError),
        (httpx.Response(200, content=b"not-json"), BpsInvalidJsonError),
    ],
)
def test_client_handles_upstream_and_json_errors(response: httpx.Response, expected: type[Exception]) -> None:
    with BpsClient("https://placeholder.invalid", transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(expected):
            client.fetch_publications()


def test_timeout_error_does_not_retain_authenticated_request() -> None:
    secret = "timeout-header-secret"

    def add_header(request: httpx.Request) -> httpx.Request:
        request.headers["X-Test-Only"] = secret
        return request

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timeout body={secret}", request=request)

    with BpsClient("https://placeholder.invalid", authenticator=add_header, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BpsTimeoutError) as error:
            client.fetch_publications()
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_network_error_does_not_retain_authenticated_request() -> None:
    secret = "network-header-secret"

    def add_header(request: httpx.Request) -> httpx.Request:
        request.headers["X-Test-Only"] = secret
        return request

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"network unavailable body={secret}", request=request)

    with BpsClient("https://placeholder.invalid", authenticator=add_header, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BpsNetworkError) as error:
            client.fetch_publications()
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_invalid_json_error_does_not_retain_response_body() -> None:
    secret = "json-body-secret"
    body = f"{{invalid token={secret}}}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body.encode(), request=request)

    with BpsClient("https://placeholder.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BpsInvalidJsonError) as error:
            client.fetch_publications()
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert body not in rendered
    assert secret not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_api_key_is_not_in_client_representation_or_errors() -> None:
    secret = "rotated-key-never-used-in-tests"

    def add_header(request: httpx.Request) -> httpx.Request:
        request.headers["X-Test-Only"] = secret
        return request

    with BpsClient("https://placeholder.invalid", authenticator=add_header, transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request))) as client:
        with pytest.raises(BpsUpstreamError) as error:
            client.fetch_publications()
        assert secret not in repr(client)
        assert secret not in str(error.value)


def test_authenticator_failure_is_safe_and_typed() -> None:
    secret = "auth-secret-never-exposed"

    def failing_authenticator(request: httpx.Request) -> httpx.Request:
        raise RuntimeError(f"credential={secret}")

    with BpsClient("https://placeholder.invalid", authenticator=failing_authenticator) as client:
        with pytest.raises(BpsAuthenticationError) as error:
            client.fetch_publications()

    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert error.value.__cause__ is None
