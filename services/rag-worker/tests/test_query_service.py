import http.client
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

from ringkas_worker.citations import CitationBuildResult
from ringkas_worker.qdrant_setup import COLLECTION_NAME
from ringkas_worker.retrieval import DenseRetrievalResult
from ringkas_worker.selection import FinalRetrievalResult
from ringkas_worker.query_service import QueryEngine, main, make_handler
from ringkas_worker.sparse_retrieval import SparseQuery, SparseRetrievalResult
from ringkas_worker.sufficiency import SufficiencyDecision
from http.server import ThreadingHTTPServer


def test_query_engine_encodes_and_retrieves_sparse_candidates_before_rrf():
    dense_result = DenseRetrievalResult(COLLECTION_NAME, 20, ())
    dense = SimpleNamespace(retrieve=lambda question: dense_result)
    sparse_result = SparseRetrievalResult(dense_result.collection_name, 20, ())
    sparse_encoder = SimpleNamespace(encode_query=lambda question: SparseQuery((1,), (1.0,)))
    sparse = SimpleNamespace(
        retrieve=lambda query: (assert_sparse_query(query), sparse_result)[1],
    )

    class Fusion:
        def fuse(self, actual_dense, sparse):
            assert actual_dense is dense_result
            assert sparse is sparse_result
            return "fused"

    selector = SimpleNamespace(select=lambda fused: FinalRetrievalResult(10, ()))
    citation_builder = SimpleNamespace(build=lambda selected: CitationBuildResult(()))
    result = SimpleNamespace(
        decision=SufficiencyDecision.INSUFFICIENT,
        usable_citation_ids=(),
        limited_citation_ids=(),
        requires_limitation=True,
        requires_refusal=True,
    )
    sufficiency = SimpleNamespace(evaluate=lambda question, selected, citations: result)

    response = QueryEngine(dense, sparse_encoder, sparse, Fusion(), selector, citation_builder, sufficiency).query("poverty")

    assert response["source_sufficiency"] == "insufficient"
    assert response["requires_refusal"] is True
    assert "score" not in json.dumps(response)


def assert_sparse_query(query):
    assert query == SparseQuery((1,), (1.0,))


def test_http_boundary_requires_token_and_valid_bounded_json():
    engine = SimpleNamespace(query=lambda question: {"source_sufficiency": "insufficient", "question_seen": question})
    token = "t" * 32
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("POST", "/retrieve", body=b'{"question":"secret query"}', headers={"Content-Type": "application/json"})
        assert connection.getresponse().status == 401
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request(
            "POST",
            "/retrieve",
            body=b'{"question":"  poverty  "}',
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["question_seen"] == "poverty"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_rejects_short_internal_token_before_startup():
    with patch.dict("os.environ", {"RAG_INTERNAL_TOKEN": "short"}, clear=True):
        assert main() == 2
