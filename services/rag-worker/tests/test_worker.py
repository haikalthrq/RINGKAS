import threading
from types import SimpleNamespace
from uuid import uuid4

import psycopg

from ringkas_worker.db.jobs import IngestionJob
from ringkas_worker.worker import PollingWorker


def settings(interval: int = 1):
    return SimpleNamespace(ingestion_poll_interval_seconds=interval)


def job() -> IngestionJob:
    from datetime import datetime, timezone

    return IngestionJob(uuid4(), "user", "running", "DKI Jakarta", 2022, 2026, 10, datetime.now(timezone.utc), None, datetime.now(timezone.utc), None)


class Repository:
    def __init__(self, queued: bool = False, claimed: IngestionJob | None = None):
        self.queued = queued
        self.claimed = claimed
        self.observations = 0
        self.claims = 0

    def has_queued_job(self):
        self.observations += 1
        return self.queued

    def claim_next_job(self):
        self.claims += 1
        return self.claimed


def test_default_worker_observes_without_claiming() -> None:
    repository = Repository(queued=True)
    assert PollingWorker(settings(), repository).run_once() is False
    assert repository.observations == 1
    assert repository.claims == 0


def test_handler_worker_claims_and_passes_typed_job() -> None:
    claimed = job()
    repository = Repository(claimed=claimed)
    received = []
    worker = PollingWorker(settings(), repository, received.append)

    assert worker.run_once() is True
    assert received == [claimed]
    assert repository.claims == 1
    assert repository.observations == 0


def test_stop_event_prevents_new_query_or_claim() -> None:
    repository = Repository(queued=True, claimed=job())
    stop_event = threading.Event()
    stop_event.set()

    assert PollingWorker(settings(), repository).run_once(stop_event) is False
    assert PollingWorker(settings(), repository, lambda _job: None).run_once(stop_event) is False
    assert repository.observations == 0
    assert repository.claims == 0


class FailingRepository(Repository):
    def has_queued_job(self):
        self.observations += 1
        raise psycopg.Error("database unavailable")


def test_database_error_uses_bounded_retry_and_stops() -> None:
    repository = FailingRepository()
    stop_event = threading.Event()

    original_wait = stop_event.wait

    def stop_after_retry(timeout=None):
        stop_event.set()
        return original_wait(0)

    stop_event.wait = stop_after_retry
    PollingWorker(settings(interval=1), repository).run(stop_event)
    assert repository.observations == 1
