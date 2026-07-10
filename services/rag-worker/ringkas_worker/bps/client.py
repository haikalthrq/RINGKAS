from collections.abc import Callable
from types import TracebackType
from typing import Self

import httpx
from pydantic import SecretStr

from ringkas_worker.bps.errors import (
    BpsAuthenticationError,
    BpsClientError,
    BpsConfigurationError,
    BpsInvalidJsonError,
    BpsNetworkError,
    BpsTimeoutError,
    BpsUpstreamError,
)
from ringkas_worker.bps.mapper import map_publications
from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.bps.urls import normalize_publications_path, validate_base_url
from ringkas_worker.config import WorkerSettings

RequestAuthenticator = Callable[[httpx.Request], httpx.Request]
PUBLICATION_QUERY = {"model": "publication", "domain": "3100", "lang": "ind"}


def query_key_authenticator(api_key: SecretStr) -> RequestAuthenticator:
    """Add BPS authentication only as the documented ``key`` query parameter."""
    if not isinstance(api_key, SecretStr) or not api_key.get_secret_value().strip():
        raise BpsConfigurationError("BPS_API_KEY is required for the official BPS client")
    key = api_key.get_secret_value()

    def authenticate(request: httpx.Request) -> httpx.Request:
        request.url = request.url.copy_merge_params({"key": key})
        return request

    return authenticate


class BpsClient:
    """HTTP boundary for the official BPS publication API contract."""

    def __init__(
        self,
        base_url: str,
        publications_path: str = "",
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        authenticator: RequestAuthenticator | None = None,
        keyword: str = "",
    ) -> None:
        if timeout <= 0:
            raise BpsConfigurationError("BPS client timeout must be positive")

        parsed_base_url = validate_base_url(base_url)
        normalized_path = normalize_publications_path(publications_path)
        base_path = parsed_base_url.path.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=parsed_base_url.copy_with(path=base_path),
            timeout=timeout,
            transport=transport,
        )
        self._publications_path = normalized_path
        self._authenticator = authenticator
        if not isinstance(keyword, str) or len(keyword) > 200:
            raise BpsConfigurationError("BPS_PUBLICATION_KEYWORD is invalid")
        self._keyword = keyword.strip()

    @classmethod
    def from_settings(
        cls,
        settings: WorkerSettings,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        authenticator: RequestAuthenticator | None = None,
    ) -> Self:
        return cls(
            settings.bps_base_url,
            settings.bps_publications_path,
            timeout=timeout,
            transport=transport,
            authenticator=authenticator or query_key_authenticator(settings.bps_api_key),
            keyword=settings.bps_publication_keyword,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_publications(self) -> list[PublicationMetadata]:
        params = dict(PUBLICATION_QUERY)
        if self._keyword:
            params["keyword"] = self._keyword
        request = self._client.build_request(
            "GET",
            self._publications_path or ".",
            params=params,
        )
        if self._authenticator is not None:
            authentication_failed = False
            try:
                request = self._authenticator(request)
            except Exception:
                authentication_failed = True
            if authentication_failed:
                raise BpsAuthenticationError("BPS authentication adapter failed") from None

        response: httpx.Response | None = None
        request_timed_out = False
        request_failed = False
        try:
            response = self._client.send(request)
        except httpx.TimeoutException:
            request_timed_out = True
        except httpx.RequestError:
            request_failed = True

        if request_timed_out:
            raise BpsTimeoutError("BPS request timed out") from None
        if request_failed:
            raise BpsNetworkError("BPS request failed") from None

        assert response is not None
        if not response.is_success:
            raise BpsUpstreamError(response.status_code)
        invalid_json = False
        payload = None
        try:
            payload = response.json()
        except ValueError:
            invalid_json = True

        if invalid_json:
            raise BpsInvalidJsonError("BPS response was not valid JSON") from None

        try:
            return map_publications(payload)
        except BpsClientError:
            raise
