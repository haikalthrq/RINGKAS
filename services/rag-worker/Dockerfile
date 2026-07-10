FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY ringkas_worker ./ringkas_worker

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 worker \
    && mkdir -p /data/ringkas/pdfs \
    && chown -R worker:worker /data/ringkas

USER worker

ENTRYPOINT ["python", "-m", "ringkas_worker"]
