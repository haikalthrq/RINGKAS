from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

from ringkas_worker.bps.errors import BpsInvalidMetadataError, BpsResponseShapeError
from ringkas_worker.bps.models import PublicationMetadata

OFFICIAL_LIST_URL = "https://webapi.bps.go.id/v1/api/list"
OFFICIAL_REGION = "DKI Jakarta"
OFFICIAL_REGION_LEVEL = "province"


def map_publications(payload: Any) -> list[PublicationMetadata]:
    """Map the official publication response where records are in ``data[1]``."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise BpsResponseShapeError("BPS response must contain a data array")
    data = payload["data"]
    if len(data) < 2 or not isinstance(data[1], list):
        raise BpsResponseShapeError("BPS response data must contain a publication array")

    publications: list[PublicationMetadata] = []
    for item in data[1]:
        if not isinstance(item, Mapping):
            raise BpsInvalidMetadataError("BPS publication item must be an object")
        try:
            release_date = _release_date(item.get("rl_date"))
            pdf_url = item.get("pdf")
            source_page_url = _source_url(pdf_url) if pdf_url else OFFICIAL_LIST_URL
            publications.append(
                PublicationMetadata(
                    external_id=_required_identifier(item.get("pub_id")),
                    title=item.get("title"),
                    publication_year=release_date.year,
                    release_date=release_date,
                    region=OFFICIAL_REGION,
                    region_level=OFFICIAL_REGION_LEVEL,
                    publication_number=_optional_text(item.get("issn")),
                    source_page_url=source_page_url,
                    pdf_url=pdf_url,
                    language="ind",
                )
            )
        except (ValidationError, ValueError, TypeError):
            # Do not expose upstream payload values, URLs, or credentials in errors.
            raise BpsInvalidMetadataError("BPS publication metadata failed validation") from None
    return publications


def _required_identifier(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError
    identifier = str(value).strip()
    if not identifier:
        raise ValueError
    return identifier


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError
    value = value.strip()
    return value or None


def _release_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError
    try:
        return date.fromisoformat(value.strip()[:10])
    except (TypeError, ValueError):
        raise ValueError from None


def _source_url(pdf_url: Any) -> str:
    if not isinstance(pdf_url, str):
        raise ValueError
    parsed = urlsplit(pdf_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
