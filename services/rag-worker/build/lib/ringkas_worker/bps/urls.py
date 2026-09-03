from urllib.parse import unquote
from urllib.parse import urlsplit

import httpx

from ringkas_worker.bps.errors import BpsConfigurationError


def validate_base_url(value: str) -> httpx.URL:
    """Validate a base endpoint without echoing the configured value."""
    if not value.strip():
        raise BpsConfigurationError("BPS_BASE_URL is required for the client")
    try:
        parsed = httpx.URL(value)
        split = urlsplit(value)
        has_userinfo = split.username is not None or split.password is not None
    except Exception:
        raise BpsConfigurationError("BPS_BASE_URL must be a valid HTTP or HTTPS URL") from None

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.is_absolute_url
        or not parsed.host
        or has_userinfo
        or parsed.query
        or parsed.fragment
    ):
        raise BpsConfigurationError("BPS_BASE_URL must be a safe absolute HTTP or HTTPS URL")
    return parsed


def normalize_publications_path(value: str) -> str:
    """Return a relative path suitable for HTTPX base_url joining."""
    if not value:
        return ""
    if value.strip() != value or not value.strip() or any(character.isspace() for character in value):
        raise BpsConfigurationError("BPS_PUBLICATIONS_PATH must be a non-whitespace relative path")
    candidate = value
    for _ in range(3):
        try:
            parsed = httpx.URL(candidate)
        except Exception:
            raise BpsConfigurationError("BPS_PUBLICATIONS_PATH must be a relative path") from None

        decoded_path = unquote(parsed.path)
        if (
            parsed.is_absolute_url
            or parsed.scheme
            or parsed.host
            or parsed.query
            or parsed.fragment
            or candidate.startswith("//")
            or any(segment == ".." for segment in decoded_path.split("/"))
        ):
            raise BpsConfigurationError("BPS_PUBLICATIONS_PATH must be a safe relative path")

        if decoded_path == parsed.path:
            return decoded_path.strip("/")
        candidate = decoded_path

    raise BpsConfigurationError("BPS_PUBLICATIONS_PATH contains encoded traversal")
