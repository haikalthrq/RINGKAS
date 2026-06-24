from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client import models

from ringkas_worker.qdrant_setup import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantCollectionSetup,
    QdrantConnectionError,
    QdrantSchemaMismatchError,
    QdrantSetupConfigurationError,
    QdrantSetupSettings,
    QdrantSetupSpec,
    SetupStatus,
)


class FakeClient:
    def __init__(self, collection=None, *, failure=None, create_result=True, create_failure=None, get_failure=None):
        self.collection = collection
        self.failure = failure
        self.create_result = create_result
        self.create_failure = create_failure
        self.get_failure = get_failure
        self.exists_calls = 0
        self.get_calls = 0
        self.create_calls = []

    def collection_exists(self, name):
        self.exists_calls += 1
        if self.failure:
            raise self.failure
        return self.collection is not None

    def get_collection(self, name):
        self.get_calls += 1
        if self.get_failure or self.failure:
            raise self.get_failure or self.failure
        return self.collection

    def create_collection(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_failure:
            raise self.create_failure
        self.collection = compatible_collection(kwargs["vectors_config"][DENSE_VECTOR_NAME].size, kwargs["vectors_config"][DENSE_VECTOR_NAME].distance)
        return self.create_result


def compatible_collection(size=384, distance=models.Distance.COSINE, *, dense_name=DENSE_VECTOR_NAME, sparse_name=SPARSE_VECTOR_NAME):
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={dense_name: models.VectorParams(size=size, distance=distance)},
                sparse_vectors={sparse_name: models.SparseVectorParams()},
            )
        )
    )


def spec(**kwargs):
    values = {"dense_size": 384, "dense_distance": "cosine"}
    values.update(kwargs)
    return QdrantSetupSpec(**values)


@pytest.mark.parametrize("value", [None, "", "not-an-integer", "1.5", "true", "0", "-1"])
def test_missing_or_invalid_dense_size_fails_before_network(monkeypatch, value):
    monkeypatch.setenv("QDRANT_DENSE_DISTANCE", "cosine")
    if value is None:
        monkeypatch.delenv("QDRANT_DENSE_VECTOR_SIZE", raising=False)
    else:
        monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", value)
    with pytest.raises(QdrantSetupConfigurationError):
        QdrantSetupSettings.from_environment()


@pytest.mark.parametrize("value", [None, "", "manhattan-ish"])
def test_missing_or_unsupported_distance_fails(monkeypatch, value):
    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "384")
    if value is None:
        monkeypatch.delenv("QDRANT_DENSE_DISTANCE", raising=False)
    else:
        monkeypatch.setenv("QDRANT_DENSE_DISTANCE", value)
    with pytest.raises(QdrantSetupConfigurationError):
        QdrantSetupSettings.from_environment()


@pytest.mark.parametrize("size", [True, False, 0, -1, "384"])
def test_spec_rejects_invalid_vector_size(size):
    with pytest.raises(QdrantSetupConfigurationError):
        QdrantSetupSpec(dense_size=size, dense_distance="cosine")


@pytest.mark.parametrize("distance", ["cosine", "dot", "euclid", "manhattan"])
def test_supported_distances_are_explicit(distance):
    assert QdrantSetupSpec(dense_size=384, dense_distance=distance).dense_distance == distance


def test_first_setup_creates_exact_named_schema():
    client = FakeClient()
    result = QdrantCollectionSetup(client).setup(spec(dense_size=512, dense_distance="dot"))
    assert result.status is SetupStatus.CREATED
    request = client.create_calls[0]
    assert request["collection_name"] == COLLECTION_NAME
    assert set(request["vectors_config"]) == {DENSE_VECTOR_NAME}
    assert request["vectors_config"][DENSE_VECTOR_NAME].size == 512
    assert request["vectors_config"][DENSE_VECTOR_NAME].distance is models.Distance.DOT
    assert set(request["sparse_vectors_config"]) == {SPARSE_VECTOR_NAME}


def test_second_setup_is_noop_without_recreation():
    client = FakeClient()
    service = QdrantCollectionSetup(client)
    assert service.setup(spec()).status is SetupStatus.CREATED
    assert service.setup(spec()).status is SetupStatus.ALREADY_COMPATIBLE
    assert len(client.create_calls) == 1
    assert not hasattr(client, "delete_collection")


def test_create_is_verified_by_get_collection():
    client = FakeClient()
    result = QdrantCollectionSetup(client).setup(spec())
    assert result.status is SetupStatus.CREATED
    assert client.get_calls == 1


def test_created_schema_mismatch_is_rejected():
    client = FakeClient()
    client.create_result = True

    def create_incompatible(**kwargs):
        client.create_calls.append(kwargs)
        client.collection = compatible_collection(999)
        return True

    client.create_collection = create_incompatible
    with pytest.raises(QdrantSchemaMismatchError):
        QdrantCollectionSetup(client).setup(spec())


def test_unsuccessful_create_cannot_produce_false_created_success():
    client = FakeClient(create_result=False)
    result = QdrantCollectionSetup(client).setup(spec())
    assert result.status is SetupStatus.ALREADY_COMPATIBLE


def test_compatible_concurrent_creation_returns_already_compatible():
    client = FakeClient(create_failure=RuntimeError("already exists"))
    client.collection = None

    def create_then_raise(**kwargs):
        client.create_calls.append(kwargs)
        client.collection = compatible_collection()
        raise RuntimeError("already exists")

    client.create_collection = create_then_raise
    result = QdrantCollectionSetup(client).setup(spec())
    assert result.status is SetupStatus.ALREADY_COMPATIBLE


def test_incompatible_concurrent_creation_raises_schema_mismatch():
    client = FakeClient()

    def create_then_raise(**kwargs):
        client.create_calls.append(kwargs)
        client.collection = compatible_collection(999)
        raise RuntimeError("already exists")

    client.create_collection = create_then_raise
    with pytest.raises(QdrantSchemaMismatchError):
        QdrantCollectionSetup(client).setup(spec())


def test_existing_compatible_collection_is_noop():
    client = FakeClient(compatible_collection())
    result = QdrantCollectionSetup(client).setup(spec())
    assert result.status is SetupStatus.ALREADY_COMPATIBLE
    assert not client.create_calls


@pytest.mark.parametrize(
    "collection",
    [
        compatible_collection(385),
        compatible_collection(distance=models.Distance.DOT),
        compatible_collection(dense_name="renamed"),
        compatible_collection(sparse_name="renamed"),
    ],
)
def test_incompatible_collection_fails_without_mutation(collection):
    client = FakeClient(collection)
    with pytest.raises(QdrantSchemaMismatchError):
        QdrantCollectionSetup(client).setup(spec())
    assert not client.create_calls


def test_client_failure_is_typed_and_sanitized():
    secret = "qdrant-api-secret"
    client = FakeClient(failure=RuntimeError(secret))
    with pytest.raises(QdrantConnectionError) as caught:
        QdrantCollectionSetup(client).setup(spec())
    error = caught.value
    assert secret not in str(error)
    assert secret not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("failure_kind", ["exists", "create", "get"])
def test_each_qdrant_operation_sanitizes_raw_failure(failure_kind):
    secret = "qdrant-api-secret"
    if failure_kind == "exists":
        client = FakeClient(failure=RuntimeError(secret))
    elif failure_kind == "create":
        client = FakeClient(create_failure=RuntimeError(secret), get_failure=RuntimeError(secret))
    else:
        client = FakeClient(compatible_collection(), get_failure=RuntimeError(secret))
    with pytest.raises(QdrantConnectionError) as caught:
        QdrantCollectionSetup(client).setup(spec())
    error = caught.value
    assert secret not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_setup_settings_masks_api_key(monkeypatch):
    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "384")
    monkeypatch.setenv("QDRANT_DENSE_DISTANCE", "cosine")
    monkeypatch.setenv("QDRANT_API_KEY", "qdrant-api-secret")
    settings = QdrantSetupSettings.from_environment()
    assert "qdrant-api-secret" not in repr(settings)
    assert settings.qdrant_api_key.get_secret_value() == "qdrant-api-secret"


@pytest.mark.parametrize("url", [
    "http://user:password@qdrant:6333",
    "http://qdrant:6333?token=qdrant-secret",
    "http://qdrant:6333/#qdrant-secret",
])
def test_qdrant_url_rejects_credentials_query_and_fragment_without_leaking_secret(monkeypatch, url):
    import traceback

    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "384")
    monkeypatch.setenv("QDRANT_DENSE_DISTANCE", "cosine")
    monkeypatch.setenv("QDRANT_URL", url)
    with pytest.raises(QdrantSetupConfigurationError) as caught:
        QdrantSetupSettings.from_environment()
    error = caught.value
    rendered = "\n".join((str(error), repr(error), "".join(traceback.format_exception(error))))
    assert "password" not in rendered
    assert "qdrant-secret" not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


def test_collection_name_is_normalized():
    assert spec(collection_name="  ringkas_chunks_test  ").collection_name == "ringkas_chunks_test"
