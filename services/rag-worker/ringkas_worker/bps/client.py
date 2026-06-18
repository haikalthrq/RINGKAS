from collections.abc import Callable
from types import TracebackType
from typing import Self

import httpx

from ringkas_worker.bps.errors import (
    BpsAuthenticationError,
    BpsClientError,
    BpsConfigurationError,
    BpsInvalidJsonError,
    BpsNetworkError,
    BpsTimeoutError,
    BpsUpstreamError,
)
from ringkas_worker.bps.mapper import map_placeholder_publications
from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.bps.urls import normalize_publications_path, validate_base_url
from ringkas_worker.config import WorkerSettings

RequestAuthenticator = Callable[[httpx.Request], httpx.Request]


class BpsClient:
    """HTTP boundary for the unverified BPS publication API contract.

    Authentication is deliberately an injected boundary. The official BPS auth
    placement and response contract must be verified before wiring it in.
    """

    def __init__(
        self,
        base_url: str,
        publications_path: str = "",
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        authenticator: RequestAuthenticator | None = None,
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
            authenticator=authenticator,
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
        request = self._client.build_request("GET", self._publications_path or ".")
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
            return map_placeholder_publications(payload)
        except BpsClientError:
            raise
