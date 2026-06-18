from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ringkas_worker.bps.errors import BpsInvalidMetadataError, BpsResponseShapeError
from ringkas_worker.bps.models import PublicationMetadata


def map_placeholder_publications(payload: Any) -> list[PublicationMetadata]:
    """Map the local placeholder contract; official BPS fields remain TBD."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        raise BpsResponseShapeError("BPS placeholder response must contain an items array")

    publications: list[PublicationMetadata] = []
    for item in payload["items"]:
        if not isinstance(item, Mapping):
            raise BpsInvalidMetadataError("BPS publication item must be an object")
        try:
            publications.append(PublicationMetadata.model_validate(item))
        except ValidationError:
            # Do not expose upstream payload values, URLs, or credentials in errors.
            raise BpsInvalidMetadataError("BPS publication metadata failed validation") from None
    return publications
