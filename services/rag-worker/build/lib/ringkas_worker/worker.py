import logging
import threading
from collections.abc import Callable

import psycopg

from ringkas_worker.config import WorkerSettings
from ringkas_worker.db.jobs import IngestionJob, IngestionJobRepository
from ringkas_worker.processor import ProcessorSystemicError

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
        try:
            self._run_handler_with_heartbeat(job)
        except ProcessorSystemicError:
            # IngestionProcessor terminalizes systemic failures before raising.
            logger.error("Ingestion job failed after terminalization")
        except Exception:
            logger.error("Ingestion job handler failed; attempting safe failure transition")
            try:
                self._repository.mark_failed(job.id, "worker handler failed")
            except Exception:
                logger.error("Ingestion job failure transition failed")
        return True

    def _run_handler_with_heartbeat(self, job: IngestionJob) -> None:
        heartbeat = getattr(self._repository, "heartbeat", None)
        if not callable(heartbeat):
            self._handler(job)
            return

        heartbeat_stop = threading.Event()
        heartbeat_interval = min(max(self._settings.ingestion_poll_interval_seconds, 1), 30)

        def keep_lease() -> None:
            while not heartbeat_stop.wait(heartbeat_interval):
                try:
                    heartbeat(job.id)
                except psycopg.Error:
                    logger.warning("Ingestion job heartbeat failed; retrying on next interval")

        heartbeat_thread = threading.Thread(target=keep_lease, name="ingestion-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:
            self._handler(job)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=heartbeat_interval + 1)

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
