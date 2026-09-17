"""Compatibility entry point; the maintained harness lives in services/rag-worker."""

from ringkas_worker.ragas_harness import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(main())  # noqa: F405
