from __future__ import annotations

import hashlib
import ipaddress
import math
import os
import socket
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import urljoin, urlsplit
import logging

import httpx

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.config import WorkerSettings

logger = logging.getLogger(__name__)


class PdfDownloadError(Exception):
    """Safe, typed failure while downloading or storing a PDF."""


class PdfUrlError(PdfDownloadError):
    pass


class PdfTimeoutError(PdfDownloadError):
    pass


class PdfNetworkError(PdfDownloadError):
    pass


class PdfResponseError(PdfDownloadError):
    pass


class PdfValidationError(PdfDownloadError):
    pass


class PdfTransportError(PdfDownloadError):
    """The downloader has no transport that can enforce destination safety."""


class PdfStorageError(PdfDownloadError):
    """A local filesystem operation failed without exposing filesystem details."""


class PdfCanonicalCorruptionError(PdfStorageError):
    """A canonical checksum path exists but does not contain its named content."""


@dataclass(frozen=True, slots=True)
class DownloadedPdf:
    checksum: str
    local_pdf_path: str
    is_duplicate: bool


_FINALIZATION_LOCK = Lock()
_PDF_SIGNATURE = b"%PDF-"
_SAFE_CONTENT_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}


class PdfDownloader:
    def __init__(
        self,
        storage_path: Path,
        *,
        allowed_hosts: set[str],
        max_size_bytes: int = 50 * 1024 * 1024,
        connect_timeout_seconds: float = 10.0,
        read_timeout_seconds: float = 60.0,
        total_timeout_seconds: float = 300.0,
        max_redirects: int = 5,
        transport: httpx.MockTransport | None = None,
    ) -> None:
        normalized_hosts = {_normalize_allowed_host(host) for host in allowed_hosts if host.strip()}
        if not normalized_hosts:
            raise PdfUrlError("PDF allowed host boundary is not configured")
        if (
            isinstance(max_size_bytes, bool)
            or not isinstance(max_size_bytes, int)
            or max_size_bytes <= 0
            or isinstance(max_redirects, bool)
            or not isinstance(max_redirects, int)
            or max_redirects < 0
            or not _is_positive_finite(connect_timeout_seconds)
            or not _is_positive_finite(read_timeout_seconds)
            or not _is_positive_finite(total_timeout_seconds)
        ):
            raise PdfValidationError("PDF download limits are invalid")
        self._root = storage_path.absolute()
        self._allowed_hosts = normalized_hosts
        self._max_size = max_size_bytes
        self._connect_timeout = float(connect_timeout_seconds)
        self._read_timeout = float(read_timeout_seconds)
        self._total_timeout = float(total_timeout_seconds)
        self._max_redirects = max_redirects
        if transport is None:
            transport = _ValidatedAddressTransport(normalized_hosts)
        elif type(transport) is not httpx.MockTransport:
            raise PdfTransportError("PDF transport is not supported")
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(read_timeout_seconds, connect=connect_timeout_seconds),
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: WorkerSettings, *, transport: httpx.MockTransport | None = None) -> PdfDownloader:
        allowed_hosts = {host.strip() for host in settings.pdf_allowed_hosts.split(",") if host.strip()}
        return cls(
            settings.pdf_storage_path,
            allowed_hosts=allowed_hosts,
            max_size_bytes=settings.pdf_max_size_bytes,
            connect_timeout_seconds=settings.pdf_connect_timeout_seconds,
            read_timeout_seconds=settings.pdf_read_timeout_seconds,
            total_timeout_seconds=settings.pdf_total_timeout_seconds,
            max_redirects=settings.pdf_max_redirects,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PdfDownloader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def download(self, publication: PublicationMetadata) -> DownloadedPdf:
        storage_failure = False
        result = None
        try:
            result = self._download(publication)
        except OSError:
            storage_failure = True
        if storage_failure:
            raise PdfStorageError("PDF storage operation failed")
        return result

    def _download(self, publication: PublicationMetadata) -> DownloadedPdf:
        if publication.pdf_url is None:
            raise PdfUrlError("publication has no PDF URL")
        current_url = str(publication.pdf_url)
        deadline = time.monotonic() + self._total_timeout
        temp_path: Path | None = None
        try:
            self._validate_url(current_url)
            if not _safe_mkdir(self._root):
                raise PdfStorageError("PDF storage is unavailable") from None
            temp = _safe_create_temp_file(self._root)
            if temp is None:
                raise PdfStorageError("PDF temporary storage is unavailable") from None
            with temp:
                temp_path = Path(temp.name)
                digest = hashlib.sha256()
                total = 0
                prefix = bytearray()
                for redirect_count in range(self._max_redirects + 1):
                    remaining = _remaining_timeout(deadline)
                    request_failure: str | None = None
                    try:
                        timeout = httpx.Timeout(
                            min(self._read_timeout, remaining),
                            connect=min(self._connect_timeout, remaining),
                        )
                        with self._client.stream(
                            "GET",
                            current_url,
                            timeout=timeout,
                            extensions={"ringkas_deadline": deadline},
                        ) as response:
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location or redirect_count == self._max_redirects:
                                    raise PdfResponseError("PDF redirect limit exceeded")
                                redirect_url = None
                                try:
                                    redirect_url = urljoin(current_url, location)
                                except (TypeError, ValueError):
                                    pass
                                if redirect_url is None:
                                    _raise_sanitized_url_error("PDF redirect URL is not allowed")
                                current_url = redirect_url
                                self._validate_url(current_url)
                                continue
                            if not 200 <= response.status_code < 300:
                                raise PdfResponseError("PDF upstream returned a non-success status")
                            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                            if content_type not in _SAFE_CONTENT_TYPES:
                                raise PdfValidationError("PDF response content type is not allowed")
                            content_length = response.headers.get("content-length")
                            if content_length is not None:
                                invalid_size = False
                                try:
                                    declared_size = int(content_length)
                                except ValueError:
                                    invalid_size = True
                                    declared_size = 0
                                if invalid_size:
                                    raise PdfValidationError("PDF response size is invalid")
                                if declared_size < 0 or declared_size > self._max_size:
                                    raise PdfValidationError("PDF response exceeds the configured size limit")
                            for chunk in response.iter_bytes(64 * 1024):
                                if _remaining_timeout(deadline) <= 0:
                                    raise PdfTimeoutError("PDF download deadline exceeded")
                                total += len(chunk)
                                if total > self._max_size:
                                    raise PdfValidationError("PDF response exceeds the configured size limit")
                                if len(prefix) < len(_PDF_SIGNATURE):
                                    prefix.extend(chunk[: len(_PDF_SIGNATURE) - len(prefix)])
                                if not _safe_write(temp, chunk):
                                    raise PdfStorageError("PDF temporary storage write failed") from None
                                digest.update(chunk)
                            _remaining_timeout(deadline)
                            break
                    except httpx.TimeoutException:
                        request_failure = "timeout"
                    except httpx.RequestError:
                        request_failure = "network"
                    if request_failure == "timeout":
                        raise PdfTimeoutError("PDF request timed out")
                    if request_failure == "network":
                        raise PdfNetworkError("PDF request failed")
                else:
                    raise PdfResponseError("PDF redirect limit exceeded")
                if bytes(prefix) != _PDF_SIGNATURE:
                    raise PdfValidationError("PDF signature is invalid")
                if not _safe_finalize_temp(temp):
                    raise PdfStorageError("PDF temporary storage finalization failed") from None
            checksum = digest.hexdigest()
            canonical = self._canonical_path(checksum)
            with _FINALIZATION_LOCK:
                canonical_exists = _safe_exists(canonical)
                if canonical_exists is None:
                    raise PdfStorageError("PDF canonical storage is unavailable") from None
                if canonical_exists:
                    verification = self._verify_file(canonical, checksum)
                    if verification == "unreadable":
                        raise PdfStorageError("PDF canonical storage cannot be read") from None
                    if verification == "corrupt":
                        raise PdfCanonicalCorruptionError("PDF canonical content is inconsistent") from None
                    return DownloadedPdf(checksum, str(canonical), True)
                # The source and destination share one filesystem; rename is atomic.
                if not _safe_replace(temp_path, canonical):
                    raise PdfStorageError("PDF canonical storage finalization failed") from None
                temp_path = None
            return DownloadedPdf(checksum, str(canonical), False)
        except PdfDownloadError:
            raise
        except ValueError:
            raise PdfUrlError("PDF URL is not allowed") from None
        finally:
            if temp_path is not None:
                _cleanup_temp_file(temp_path)

    def _canonical_path(self, checksum: str) -> Path:
        path = (self._root / f"{checksum}.pdf").absolute()
        if path.parent != self._root:
            raise PdfValidationError("PDF path escaped storage root")
        return path

    @staticmethod
    def _verify_file(path: Path, expected_checksum: str) -> str | None:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(64 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return "unreadable"
        if digest.hexdigest() != expected_checksum:
            return "corrupt"
        return None

    def _validate_url(self, value: str) -> None:
        invalid = False
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
            if parsed.scheme.lower() not in {"http", "https"} or not host:
                raise ValueError
            if parsed.username is not None or parsed.password is not None or parsed.fragment:
                raise ValueError
            normalized = host.lower().rstrip(".")
            if not _is_allowed_host(normalized, self._allowed_hosts):
                raise ValueError
            addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            try:
                addresses.append(ipaddress.ip_address(normalized))
            except ValueError:
                pass
            if addresses and any(not _is_public(item) for item in addresses):
                raise ValueError
            parsed.port  # validate malformed ports
        except (ValueError, OSError):
            invalid = True
        if invalid:
            raise PdfUrlError("PDF URL is not allowed")


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or getattr(address, "is_site_local", False)
    )


def _is_positive_finite(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        return False
    return math.isfinite(converted) and converted > 0


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PdfTimeoutError("PDF download deadline exceeded")
    return remaining


class _ValidatedAddressTransport(httpx.BaseTransport):
    """Resolve each request before connecting, without trusting DNS blindly."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        self._allowed_hosts = allowed_hosts
        self._transport: httpx.BaseTransport | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        original_url = request.url
        original_host = original_url.host
        deadline = request.extensions.get("ringkas_deadline")
        addresses = _resolve_public_addresses(original_url, self._allowed_hosts, deadline)
        last_error: httpx.RequestError | None = None
        for address in addresses:
            remaining = _remaining_timeout(deadline) if isinstance(deadline, (int, float)) else None
            pinned_request = _pinned_request(request, original_url, original_host, address, remaining)
            owned_transport = self._transport is None
            inner = self._transport or httpx.HTTPTransport(trust_env=False, proxy=None)
            try:
                response = inner.handle_request(pinned_request)
                if owned_transport:
                    try:
                        response = httpx.Response(
                            response.status_code,
                            headers=response.headers,
                            stream=_OwnedResponseStream(response, inner),
                            extensions=response.extensions,
                        )
                    except BaseException:
                        try:
                            response.close()
                        except BaseException:
                            pass
                        try:
                            inner.close()
                        except BaseException:
                            pass
                        raise
                return response
            except httpx.RequestError as error:
                last_error = error
                if owned_transport:
                    inner.close()
            except OSError:
                last_error = httpx.ConnectError("PDF connection failed", request=pinned_request)
                if owned_transport:
                    inner.close()
        if last_error is not None:
            raise last_error
        raise httpx.ConnectError("PDF connection failed", request=request)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()


def _resolve_public_addresses(
    url: httpx.URL,
    allowed_hosts: set[str],
    deadline: float | None = None,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        if deadline is not None:
            _remaining_timeout(deadline)
        host = url.host
        normalized = host.lower().rstrip(".") if host else ""
        if url.scheme.lower() not in {"http", "https"} or not host:
            raise ValueError
        if url.username or url.password or url.fragment:
            raise ValueError
        if not _is_allowed_host(normalized, allowed_hosts):
            raise ValueError
        try:
            addresses = [ipaddress.ip_address(normalized)]
        except ValueError:
            resolved = socket.getaddrinfo(host, url.port, type=socket.SOCK_STREAM)
            if not resolved:
                raise ValueError
            addresses = [ipaddress.ip_address(item[4][0]) for item in resolved]
        if deadline is not None:
            _remaining_timeout(deadline)
        if not addresses or any(not _is_public(address) for address in addresses):
            raise ValueError
        return tuple(dict.fromkeys(addresses))
    except (IndexError, OSError, TypeError, ValueError):
        raise httpx.ConnectError("PDF destination is not allowed", request=None) from None


def _host_header(url: httpx.URL) -> str:
    host = url.host
    if ":" in host:
        host = f"[{host}]"
    if url.port is not None and url.port != (443 if url.scheme.lower() == "https" else 80):
        return f"{host}:{url.port}"
    return host


def _pinned_request(
    request: httpx.Request,
    original_url: httpx.URL,
    original_host: str,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    remaining: float | None = None,
) -> httpx.Request:
    safe_headers = {"accept", "accept-encoding", "range", "user-agent"}
    headers = httpx.Headers(
        {
            key: value
            for key, value in request.headers.multi_items()
            if key.lower() in safe_headers
        }
    )
    headers["Host"] = _host_header(original_url)
    extensions = dict(request.extensions)
    if remaining is not None:
        timeout = dict(extensions.get("timeout", {}))
        for phase in ("connect", "read", "write", "pool"):
            value = timeout.get(phase)
            if isinstance(value, (int, float)):
                timeout[phase] = min(value, remaining)
        extensions["timeout"] = timeout
    if original_url.scheme.lower() == "https":
        extensions["sni_hostname"] = original_host
    return httpx.Request(
        request.method,
        original_url.copy_with(host=address.compressed),
        headers=headers,
        content=request.content,
        extensions=extensions,
    )


class _OwnedResponseStream(httpx.SyncByteStream):
    def __init__(self, response: httpx.Response, transport: httpx.BaseTransport) -> None:
        self._response = response
        self._transport = transport
        self._closed = False

    def __iter__(self):
        try:
            yield from self._response.stream
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        finally:
            self._transport.close()


def _is_allowed_host(host: str, allowed_hosts: set[str]) -> bool:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return any(
            host == allowed or host.endswith("." + allowed)
            for allowed in allowed_hosts
            if not _is_ip_literal(allowed)
        )
    return literal.compressed in allowed_hosts


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _raise_sanitized_url_error(message: str) -> None:
    error = PdfUrlError(message)
    error.__cause__ = None
    error.__context__ = None
    raise error


def _normalize_allowed_host(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if not candidate or "*" in candidate:
        raise PdfUrlError("PDF allowed host boundary is invalid")
    if candidate.startswith("["):
        if not candidate.endswith("]"):
            raise PdfUrlError("PDF allowed host boundary is invalid")
        try:
            address = ipaddress.ip_address(candidate[1:-1])
        except ValueError:
            raise PdfUrlError("PDF allowed host boundary is invalid") from None
        if not isinstance(address, ipaddress.IPv6Address) or not _is_public(address):
            raise PdfUrlError("PDF allowed host boundary is invalid")
        return address.compressed
    if ":" in candidate:
        raise PdfUrlError("PDF IPv6 literals must be bracketed")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is not None:
        if not isinstance(address, ipaddress.IPv4Address) or not _is_public(address):
            raise PdfUrlError("PDF allowed host boundary is invalid")
        return address.compressed
    invalid = False
    try:
        parsed = urlsplit("//" + candidate)
        if parsed.hostname != candidate or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.path or parsed.query or parsed.fragment or parsed.port is not None:
            raise ValueError
    except (ValueError, TypeError):
        invalid = True
    if invalid:
        raise PdfUrlError("PDF allowed host boundary is invalid")
    return candidate


def _cleanup_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("PDF temporary file cleanup failed")


def _safe_mkdir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return True


def _safe_create_temp_file(root: Path):
    try:
        return tempfile.NamedTemporaryFile(prefix=".ringkas-", suffix=".part", dir=root, delete=False)
    except OSError:
        return None


def _safe_write(stream, chunk: bytes) -> bool:
    try:
        stream.write(chunk)
    except OSError:
        return False
    return True


def _safe_finalize_temp(stream) -> bool:
    try:
        stream.flush()
        os.fsync(stream.fileno())
    except OSError:
        return False
    return True


def _safe_exists(path: Path) -> bool | None:
    try:
        return path.exists()
    except OSError:
        return None


def _safe_replace(source: Path, target: Path) -> bool:
    try:
        os.replace(source, target)
    except OSError:
        return False
    return True
