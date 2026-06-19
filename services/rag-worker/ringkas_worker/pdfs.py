from __future__ import annotations

import hashlib
import ipaddress
import os
import tempfile
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
        max_redirects: int = 5,
        transport: httpx.MockTransport | None = None,
    ) -> None:
        if type(transport) is not httpx.MockTransport:
            raise PdfTransportError("PDF live transport is disabled")
        normalized_hosts = {_normalize_allowed_host(host) for host in allowed_hosts if host.strip()}
        if not normalized_hosts:
            raise PdfUrlError("PDF allowed host boundary is not configured")
        if max_size_bytes <= 0 or max_redirects < 0:
            raise PdfValidationError("PDF download limits are invalid")
        self._root = storage_path.absolute()
        self._allowed_hosts = normalized_hosts
        self._max_size = max_size_bytes
        self._max_redirects = max_redirects
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
                    request_failure: str | None = None
                    try:
                        with self._client.stream("GET", current_url) as response:
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location or redirect_count == self._max_redirects:
                                    raise PdfResponseError("PDF redirect limit exceeded")
                                current_url = urljoin(current_url, location)
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
                                total += len(chunk)
                                if total > self._max_size:
                                    raise PdfValidationError("PDF response exceeds the configured size limit")
                                if len(prefix) < len(_PDF_SIGNATURE):
                                    prefix.extend(chunk[: len(_PDF_SIGNATURE) - len(prefix)])
                                if not _safe_write(temp, chunk):
                                    raise PdfStorageError("PDF temporary storage write failed") from None
                                digest.update(chunk)
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
        except (PdfDownloadError, ValueError):
            raise
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
            if not any(normalized == allowed or normalized.endswith("." + allowed) for allowed in self._allowed_hosts):
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
    return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified)


def _normalize_allowed_host(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if not candidate or "*" in candidate:
        raise PdfUrlError("PDF allowed host boundary is invalid")
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
