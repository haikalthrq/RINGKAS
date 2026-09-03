from collections.abc import Callable
from types import TracebackType
from typing import Self
from time import sleep

import httpx
from pydantic import SecretStr

from ringkas_worker.bps.errors import (
    BpsAuthenticationError,
    BpsClientError,
    BpsConfigurationError,
    BpsInvalidJsonError,
    BpsNetworkError,
    BpsResponseShapeError,
    BpsTimeoutError,
    BpsUpstreamError,
)
from ringkas_worker.bps.mapper import map_publications
from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.bps.urls import normalize_publications_path, validate_base_url
from ringkas_worker.config import WorkerSettings

RequestAuthenticator = Callable[[httpx.Request], httpx.Request]
PUBLICATION_QUERY = {"model": "publication", "domain": "3100", "lang": "ind"}
MAX_REQUEST_ATTEMPTS = 3


def _raise_safe(error: BpsClientError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error from None


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
        publications: list[PublicationMetadata] = []
        page = 1
        while True:
            page_params = params if page == 1 else {**params, "page": page}
            payload = self._fetch_payload(page_params)
            publications.extend(map_publications(payload))
            pages = _page_count(payload)
            if page >= pages:
                return publications
            page += 1

    def _fetch_payload(self, params: dict[str, str | int]) -> object:
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            request = self._client.build_request(
                "GET",
                self._publications_path or ".",
                params=params,
            )
            if self._authenticator is not None:
                try:
                    request = self._authenticator(request)
                except Exception:
                    raise BpsAuthenticationError("BPS authentication adapter failed") from None

            request_timed_out = False
            request_failed = False
            try:
                response = self._client.send(request)
            except httpx.TimeoutException:
                request_timed_out = True
            except httpx.RequestError:
                request_failed = True

            if request_timed_out:
                if attempt < MAX_REQUEST_ATTEMPTS - 1:
                    sleep(0.25 * (attempt + 1))
                    continue
                _raise_safe(BpsTimeoutError("BPS request timed out"))
            if request_failed:
                if attempt < MAX_REQUEST_ATTEMPTS - 1:
                    sleep(0.25 * (attempt + 1))
                    continue
                _raise_safe(BpsNetworkError("BPS request failed"))

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_REQUEST_ATTEMPTS - 1:
                    response.close()
                    sleep(0.25 * (attempt + 1))
                    continue
            if not response.is_success:
                raise BpsUpstreamError(response.status_code)
            invalid_json = False
            try:
                payload = response.json()
            except ValueError:
                invalid_json = True
            if invalid_json:
                _raise_safe(BpsInvalidJsonError("BPS response was not valid JSON"))

            return payload
        _raise_safe(BpsNetworkError("BPS request failed"))


def _page_count(payload: object) -> int:
    if not isinstance(payload, dict):
        _raise_safe(BpsResponseShapeError("BPS response has an invalid pagination container"))
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        _raise_safe(BpsResponseShapeError("BPS response has an invalid pagination container"))
    pages = data[0].get("pages", 1)
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 1000:
        _raise_safe(BpsResponseShapeError("BPS response has an invalid page count"))
    return pages
