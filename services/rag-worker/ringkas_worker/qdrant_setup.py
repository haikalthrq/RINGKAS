from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, SecretStr, TypeAdapter, ValidationError
from qdrant_client import QdrantClient, models

from ringkas_worker.dimension import DimensionVerificationError, verify_live_dimension_from_environment


LEGACY_COLLECTION_NAME = "ringkas_chunks_v1"
COLLECTION_NAME = "ringkas_chunks_cf_qwen3_embedding_v1"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
SCHEMA_VERSION = 1
SUPPORTED_DISTANCES = ("cosine", "dot", "euclid", "manhattan")


class QdrantSetupError(Exception):
    """Base class for safe, typed collection setup failures."""

    code = "qdrant_setup_error"


class QdrantSetupConfigurationError(QdrantSetupError):
    code = "invalid_qdrant_setup_configuration"


class QdrantSchemaMismatchError(QdrantSetupError):
    code = "qdrant_schema_mismatch"


class QdrantConnectionError(QdrantSetupError):
    code = "qdrant_connection_error"


class SetupStatus(str, Enum):
    CREATED = "created"
    ALREADY_COMPATIBLE = "already_compatible"


@dataclass(frozen=True, slots=True)
class QdrantSetupSpec:
    """The immutable schema contract required to create the collection."""

    dense_size: int
    dense_distance: str
    collection_name: str = COLLECTION_NAME

    def __post_init__(self) -> None:
        if isinstance(self.dense_size, bool) or not isinstance(self.dense_size, int) or self.dense_size <= 0:
            raise QdrantSetupConfigurationError("dense vector size must be a positive integer")
        if not isinstance(self.dense_distance, str) or self.dense_distance.strip().lower() not in SUPPORTED_DISTANCES:
            raise QdrantSetupConfigurationError(
                "dense distance must be one of: " + ", ".join(SUPPORTED_DISTANCES)
            )
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            raise QdrantSetupConfigurationError("collection name must not be empty")
        object.__setattr__(self, "collection_name", self.collection_name.strip())
        object.__setattr__(self, "dense_distance", self.dense_distance.strip().lower())
        if self.collection_name != COLLECTION_NAME:
            raise QdrantSetupConfigurationError(
                f"collection name must be {COLLECTION_NAME}"
            )


@dataclass(frozen=True, slots=True)
class QdrantSetupResult:
    status: SetupStatus
    collection_name: str


@dataclass(frozen=True, slots=True)
class QdrantSetupSettings:
    """Setup-only environment configuration; ordinary worker startup does not use it."""

    qdrant_url: str
    qdrant_api_key: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    spec: QdrantSetupSpec | None = None

    @classmethod
    def from_environment(cls) -> QdrantSetupSettings:
        raw_size = os.getenv("QDRANT_DENSE_VECTOR_SIZE")
        raw_distance = os.getenv("QDRANT_DENSE_DISTANCE")
        if raw_size is None or not raw_size.strip() or raw_distance is None or not raw_distance.strip():
            raise QdrantSetupConfigurationError(
                "QDRANT_DENSE_VECTOR_SIZE and QDRANT_DENSE_DISTANCE are required for collection setup"
            )
        try:
            url = str(TypeAdapter(AnyHttpUrl).validate_python(os.getenv("QDRANT_URL", "http://qdrant:6333")))
        except (ValidationError, ValueError, TypeError):
            url = ""
            url_error = QdrantSetupConfigurationError("QDRANT_URL must be a valid HTTP or HTTPS URL")
        else:
            url_error = None
        if url_error is not None:
            _raise_sanitized(url_error)
        parsed_url = urlsplit(url)
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise QdrantSetupConfigurationError(
                "QDRANT_URL must not contain credentials, query parameters, or fragments"
            )
        try:
            size = int(raw_size)
        except (TypeError, ValueError):
            size = 0
            size_error = QdrantSetupConfigurationError("QDRANT_DENSE_VECTOR_SIZE must be a positive integer")
        else:
            size_error = None
        if size_error is not None:
            _raise_sanitized(size_error)
        spec = QdrantSetupSpec(
            dense_size=size,
            dense_distance=raw_distance,
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", COLLECTION_NAME),
        )
        return cls(
            qdrant_url=url,
            qdrant_api_key=SecretStr(os.getenv("QDRANT_API_KEY", "")),
            spec=spec,
        )


@runtime_checkable
class CollectionSetupClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool: ...

    def get_collection(self, collection_name: str) -> Any: ...

    def create_collection(self, *, collection_name: str, vectors_config: Any, sparse_vectors_config: Any) -> Any: ...


class QdrantCollectionSetup:
    def __init__(self, client: CollectionSetupClient) -> None:
        self._client = client

    def setup(self, spec: QdrantSetupSpec) -> QdrantSetupResult:
        if not isinstance(spec, QdrantSetupSpec):
            raise QdrantSetupConfigurationError("setup specification has an invalid type")
        try:
            exists = self._client.collection_exists(spec.collection_name)
        except Exception:
            error = QdrantConnectionError("could not check the Qdrant collection")
        else:
            error = None
        if error is not None:
            _raise_sanitized(error)
        if not exists:
            create_succeeded = False
            try:
                create_result = self._client.create_collection(
                    collection_name=spec.collection_name,
                    vectors_config={
                        DENSE_VECTOR_NAME: models.VectorParams(
                            size=spec.dense_size,
                            distance=_distance_model(spec.dense_distance),
                        )
                    },
                    sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
                )
                create_succeeded = create_result is True
            except Exception:
                create_succeeded = False
            collection = _inspect_collection(self._client, spec)
            if collection is None:
                _raise_sanitized(QdrantConnectionError("could not create the Qdrant collection"))
            if not _schema_matches(collection, spec):
                _raise_sanitized(QdrantSchemaMismatchError("created Qdrant collection has an incompatible schema"))
            return QdrantSetupResult(
                SetupStatus.CREATED if create_succeeded else SetupStatus.ALREADY_COMPATIBLE,
                spec.collection_name,
            )

        collection = _inspect_collection(self._client, spec)
        if collection is None:
            _raise_sanitized(QdrantConnectionError("could not inspect the Qdrant collection"))
        if not _schema_matches(collection, spec):
            _raise_sanitized(QdrantSchemaMismatchError("existing Qdrant collection has an incompatible schema"))
        return QdrantSetupResult(SetupStatus.ALREADY_COMPATIBLE, spec.collection_name)


def _inspect_collection(client: CollectionSetupClient, spec: QdrantSetupSpec) -> Any | None:
    try:
        return client.get_collection(spec.collection_name)
    except Exception:
        return None


def _raise_sanitized(error: QdrantSetupError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _distance_model(distance: str) -> models.Distance:
    return models.Distance[distance.upper()]


def _schema_matches(collection: Any, spec: QdrantSetupSpec) -> bool:
    params = getattr(getattr(collection, "config", None), "params", None)
    vectors = getattr(params, "vectors", None)
    sparse_vectors = getattr(params, "sparse_vectors", None)
    if not isinstance(vectors, dict) or set(vectors) != {DENSE_VECTOR_NAME}:
        return False
    if not isinstance(sparse_vectors, dict) or set(sparse_vectors) != {SPARSE_VECTOR_NAME}:
        return False
    dense = vectors[DENSE_VECTOR_NAME]
    return getattr(dense, "size", None) == spec.dense_size and _distance_value(getattr(dense, "distance", None)) == spec.dense_distance


def _distance_value(value: Any) -> str | None:
    candidate = getattr(value, "value", value)
    if not isinstance(candidate, str):
        return None
    return candidate.rsplit(".", 1)[-1].lower()


def main() -> int:
    logger = logging.getLogger(__name__)
    try:
        verified = verify_live_dimension_from_environment()
        settings = QdrantSetupSettings.from_environment()
        assert settings.spec is not None
        if settings.spec.dense_size != verified.dimension:
            raise DimensionVerificationError("live embedding dimension does not match configuration")
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value() or None)
        result = QdrantCollectionSetup(client).setup(settings.spec)
    except DimensionVerificationError:
        logger.error("Qdrant collection setup failed [embedding_dimension_verification_failed]")
        return 2
    except QdrantSetupError as error:
        logger.error("Qdrant collection setup failed [%s]: %s", error.code, str(error))
        return 2
    except Exception:
        logger.error("Qdrant collection setup failed [qdrant_connection_error]")
        return 2
    logger.info("Qdrant collection %s: %s", result.collection_name, result.status.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
