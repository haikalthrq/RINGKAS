import logging
import threading
from collections.abc import Callable

import psycopg

from ringkas_worker.config import WorkerSettings
from ringkas_worker.db.jobs import IngestionJob, IngestionJobRepository

logger = logging.getLogger(__name__)
JobHandler = Callable[[IngestionJob], None]


class PollingWorker:
    def __init__(self, settings: WorkerSettings, repository: IngestionJobRepository, handler: JobHandler | None = None) -> None:
        self._settings = settings
        self._repository = repository
        self._handler = handler
        self._last_queue_state: bool | None = None

    def run_once(self, stop_event: threading.Event | None = None) -> bool:
        if stop_event is not None and stop_event.is_set():
            return False
        if self._handler is None:
            has_queued_job = self._repository.has_queued_job()
            if has_queued_job != self._last_queue_state:
                logger.info(
                    "Queued job observed=%s; processor unavailable, atomic claim remains disabled",
                    has_queued_job,
                )
                self._last_queue_state = has_queued_job
            return False
        if stop_event is not None and stop_event.is_set():
            return False
        job = self._repository.claim_next_job()
        if job is None:
            return False
        self._handler(job)
        return True

    def run(self, stop_event: threading.Event) -> None:
        retry_delay = min(max(self._settings.ingestion_poll_interval_seconds, 1), 60)
        while not stop_event.is_set():
            try:
                if stop_event.is_set():
                    break
                self.run_once(stop_event)
                retry_delay = min(max(self._settings.ingestion_poll_interval_seconds, 1), 60)
            except psycopg.Error:
                logger.warning("Database operation failed; retrying with bounded backoff")
                stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
                continue
            stop_event.wait(self._settings.ingestion_poll_interval_seconds)
