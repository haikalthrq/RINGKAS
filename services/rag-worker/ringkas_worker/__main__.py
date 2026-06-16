import logging
import signal
import threading

from pydantic import ValidationError

from ringkas_worker.config import WorkerSettings
from ringkas_worker.db.jobs import IngestionJobRepository
from ringkas_worker.logging_config import configure_logging
from ringkas_worker.worker import PollingWorker


def main() -> int:
    configure_logging()
    logger = logging.getLogger(__name__)
    try:
        settings = WorkerSettings()
    except ValidationError:
        logger.error("Invalid worker configuration; check required environment variables and safe ranges")
        return 2

    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame) -> None:
        logger.info("Shutdown signal received; no new jobs will be claimed")
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    PollingWorker(
        settings,
        IngestionJobRepository(
            settings.database_url.get_secret_value(),
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        ),
    ).run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
