import logging
import signal
import threading
from contextlib import ExitStack

from pydantic import ValidationError

from ringkas_worker.bps.client import BpsClient
from ringkas_worker.chunking import RecursiveTextChunker
from ringkas_worker.cleaning import ConservativeTextCleaner
from ringkas_worker.config import WorkerSettings
from ringkas_worker.db.chunks import ChunkRepository
from ringkas_worker.db.documents import DocumentRepository
from ringkas_worker.db.jobs import IngestionJobRepository
from ringkas_worker.db.logs import IngestionLogRepository
from ringkas_worker.indexing import QdrantChunkIndexer
from ringkas_worker.logging_config import configure_logging
from ringkas_worker.parsers import PyMuPDFParser
from ringkas_worker.pdfs import PdfDownloader
from ringkas_worker.processor import IngestionProcessor
from ringkas_worker.worker import PollingWorker


def _close_resource(resource: object) -> None:
    close = getattr(resource, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        logging.getLogger(__name__).warning("Worker resource cleanup failed")


def build_processor(settings: WorkerSettings, resources: ExitStack) -> IngestionProcessor:
    database_url = settings.database_url.get_secret_value()
    jobs = IngestionJobRepository(
        database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
        statement_timeout_ms=settings.database_statement_timeout_ms,
    )
    publications = BpsClient.from_settings(settings)
    resources.callback(_close_resource, publications)
    downloader = PdfDownloader.from_settings(settings)
    resources.callback(_close_resource, downloader)
    indexer = QdrantChunkIndexer.from_environment()
    resources.callback(_close_resource, indexer)
    return IngestionProcessor(
        publications=publications,
        downloader=downloader,
        parser=PyMuPDFParser(),
        cleaner=ConservativeTextCleaner(),
        chunker=RecursiveTextChunker(chunk_size=settings.chunk_size_max, length_function=len),
        indexer=indexer,
        jobs=jobs,
        documents=DocumentRepository(database_url),
        chunks=ChunkRepository(database_url),
        logs=IngestionLogRepository(
            database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        ),
    )


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
    resources = ExitStack()
    try:
        processor = build_processor(settings, resources)
        worker = PollingWorker(settings, processor.jobs, processor)
    except Exception:
        resources.close()
        logger.error("Worker startup failed; check required environment variables and service configuration")
        return 2
    with resources:
        worker.run(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
