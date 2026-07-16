from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ringkas_worker.citations import GroundedCitationBuilder
from ringkas_worker.db.citations import PostgresCitationSourceRepository
from ringkas_worker.fusion import RrfFusion, RrfSettings
from ringkas_worker.retrieval import QdrantDenseRetriever
from ringkas_worker.selection import FinalSelectionSettings, FinalTopKSelector
from ringkas_worker.sparse_retrieval import (
    FastEmbedSparseEncoder,
    QdrantSparseRetriever,
    SparseEncoder,
    SparseRetrievalSettings,
    qdrant_client_from_settings,
)
from ringkas_worker.sufficiency import QualitativeRetrievalSufficiencyEvaluator

MAX_REQUEST_BYTES = 16 * 1024
MAX_QUESTION_CHARS = 2_000


def _valid_token(token: str) -> bool:
    return len(token) >= 32 and token == token.strip() and not any(character.isspace() for character in token)


class QueryEngine:
    def __init__(self, dense, sparse_encoder: SparseEncoder, sparse, fusion, selector, citation_builder, sufficiency) -> None:
        self._dense = dense
        self._sparse_encoder = sparse_encoder
        self._sparse = sparse
        self._fusion = fusion
        self._selector = selector
        self._citation_builder = citation_builder
        self._sufficiency = sufficiency

    @classmethod
    def from_environment(cls) -> QueryEngine:
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url.strip():
            raise ValueError("DATABASE_URL is required")
        dense = QdrantDenseRetriever.from_environment()
        sparse_client = None
        try:
            sparse_settings = SparseRetrievalSettings.from_environment()
            sparse_encoder = FastEmbedSparseEncoder.from_environment()
            sparse_client = qdrant_client_from_settings(sparse_settings)
            return cls(
                dense,
                sparse_encoder,
                QdrantSparseRetriever(sparse_client, sparse_settings, _owned_clients=(sparse_client,)),
                RrfFusion(RrfSettings.from_environment()),
                FinalTopKSelector(FinalSelectionSettings.from_environment()),
                GroundedCitationBuilder(PostgresCitationSourceRepository(database_url)),
                QualitativeRetrievalSufficiencyEvaluator.default(),
            )
        except Exception:
            if sparse_client is not None:
                sparse_client.close()
            dense.close()
            raise

    def close(self) -> None:
        self._dense.close()
        self._sparse.close()

    def query(self, question: str) -> dict[str, Any]:
        dense = self._dense.retrieve(question)
        sparse = self._sparse.retrieve(self._sparse_encoder.encode_query(question))
        selected = self._selector.select(self._fusion.fuse(dense, sparse))
        citations = self._citation_builder.build(selected)
        sufficiency = self._sufficiency.evaluate(question, selected, citations)
        allowed_ids = set(sufficiency.usable_citation_ids + sufficiency.limited_citation_ids)
        visible = citations.citations if sufficiency.requires_refusal else tuple(
            citation for citation in citations.citations if citation.chunk_id in allowed_ids
        )
        reason = None
        if sufficiency.requires_refusal:
            reason = "No sufficiently relevant citable evidence was found."
        elif sufficiency.requires_limitation:
            reason = "Retrieved evidence is limited; the answer must state this limitation."
        return {
            "source_sufficiency": sufficiency.decision.value,
            "requires_limitation": sufficiency.requires_limitation,
            "requires_refusal": sufficiency.requires_refusal,
            "limitation_reason": reason,
            "citations": [
                {
                    "document_id": citation.document_id,
                    "chunk_id": citation.chunk_id,
                    "title": citation.title,
                    "year": citation.publication_year,
                    "region": citation.region,
                    "page_start": citation.page_start,
                    "page_end": citation.page_end,
                    "source_url": citation.source_url,
                    "snippet": citation.excerpt,
                }
                for citation in visible
            ],
        }


def make_handler(engine: QueryEngine, token: str) -> type[BaseHTTPRequestHandler]:
    if not _valid_token(token):
        raise ValueError("invalid internal token")

    class RetrievalHandler(BaseHTTPRequestHandler):
        server_version = "RINGKAS"
        sys_version = ""

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:
            if self.path != "/retrieve":
                self._reply(404, {"error": "not_found"})
                return
            authorization = self.headers.get("Authorization", "")
            supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied, token):
                self._reply(401, {"error": "unauthorized"})
                return
            if self.headers.get_content_type() != "application/json":
                self._reply(415, {"error": "unsupported_media_type"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 1 or length > MAX_REQUEST_BYTES:
                self._reply(413, {"error": "invalid_request_size"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._reply(400, {"error": "invalid_json"})
                return
            if not isinstance(payload, dict) or set(payload) != {"question"}:
                self._reply(400, {"error": "invalid_request"})
                return
            question = payload["question"]
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
                self._reply(400, {"error": "invalid_question"})
                return
            try:
                result = engine.query(question.strip())
            except Exception:
                self._reply(503, {"error": "retrieval_unavailable"})
                return
            self._reply(200, result)

        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return RetrievalHandler


def main() -> int:
    token = os.getenv("RAG_INTERNAL_TOKEN", "")
    if not _valid_token(token):
        return 2
    try:
        engine = QueryEngine.from_environment()
        port = int(os.getenv("RAG_QUERY_PORT", "8081"))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(engine, token))
    except Exception:
        return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
