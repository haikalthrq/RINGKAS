from datetime import date
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
from ringkas_worker.bps.mapper import map_placeholder_publications


PLACEHOLDER_PAYLOAD = {
    "items": [
        {
            "external_id": "placeholder-1",
            "title": "Placeholder publication",
            "publication_year": 2025,
            "release_date": "2025-06-01",
            "region": "DKI Jakarta",
            "region_level": "province",
            "topic": "Population",
            "source_page_url": "https://example.invalid/publication/1",
            "pdf_url": "https://example.invalid/publication/1.pdf",
        }
    ]
}


def test_placeholder_fixture_maps_required_and_optional_metadata() -> None:
    publication = map_placeholder_publications(PLACEHOLDER_PAYLOAD)[0]

    assert publication.title == "Placeholder publication"
    assert publication.publication_year == 2025
    assert publication.release_date == date(2025, 6, 1)
    assert publication.region == "DKI Jakarta"
    assert publication.pdf_url is not None


@pytest.mark.parametrize(
    "item",
    [
        {"publication_year": 2025, "region": "DKI Jakarta", "region_level": "province", "source_page_url": "https://example.invalid"},
        {"title": "Title", "region": "DKI Jakarta", "region_level": "province", "source_page_url": "https://example.invalid"},
        {"title": "Title", "publication_year": 0, "region": "DKI Jakarta", "region_level": "province", "source_page_url": "https://example.invalid"},
        {"title": "Title", "publication_year": 2025, "region": "DKI Jakarta", "region_level": "province"},
    ],
)
def test_invalid_metadata_is_rejected(item: dict[str, object]) -> None:
    with pytest.raises(BpsInvalidMetadataError):
        map_placeholder_publications({"items": [item]})


@pytest.mark.parametrize(
    "source_page_url",
    [
        "https://user:password@example.invalid/publication",
        "https://example.invalid/publication?token=secret-token",
    ],
)
def test_invalid_metadata_error_does_not_retain_upstream_url(source_page_url: str) -> None:
    with pytest.raises(BpsInvalidMetadataError) as error:
        map_placeholder_publications(
            {
                "items": [
                    {
                        "title": "Title",
                        "publication_year": 2025,
                        "region": "DKI Jakarta",
                        "region_level": "province",
                        "source_page_url": source_page_url,
                    }
                ]
            }
        )

    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert source_page_url not in rendered
    assert error.value.__cause__ is None


def test_optional_metadata_can_be_absent() -> None:
    publication = map_placeholder_publications(
        {"items": [{"title": "Title", "publication_year": 2025, "region": "DKI Jakarta", "region_level": "province", "source_page_url": "https://example.invalid"}]}
    )[0]
    assert publication.external_id is None
    assert publication.pdf_url is None


def test_invalid_response_shape_is_rejected() -> None:
    with pytest.raises(BpsResponseShapeError):
        map_placeholder_publications({"data": []})


def test_client_builds_configured_path_and_uses_mock_transport() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PLACEHOLDER_PAYLOAD, request=request)

    with BpsClient(
        "https://placeholder.invalid/api/",
        "publications",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.fetch_publications()

    assert str(seen[0].url) == "https://placeholder.invalid/api/publications"


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
        return httpx.Response(200, json=PLACEHOLDER_PAYLOAD, request=request)

    with BpsClient(
        "https://placeholder.invalid/api/",
        "/nested/publications/",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.fetch_publications()

    assert str(seen[0].url) == "https://placeholder.invalid/api/nested/publications"


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
