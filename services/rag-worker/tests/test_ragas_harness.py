import json
from pathlib import Path

import ringkas_worker.ragas_harness as harness
from ringkas_worker.evaluation_dataset import APPROVED_QUESTION_TYPES, DATASET_PATH
from ringkas_worker.ragas_harness import DEFAULT_FIXTURE_PATH, run_sample


def test_deterministic_sample_is_explicitly_fixture_validation() -> None:
    result = run_sample(responses_path=DEFAULT_FIXTURE_PATH)

    assert result["status"] == "fixture_validated"
    assert result["evaluation_label"] == "deterministic harness validation"
    assert result["metrics"] is None
    assert result["dataset_capacity"] == 100


def test_sample_output_is_machine_readable(capsys) -> None:
    from ringkas_worker.ragas_harness import main

    assert main(["--mode", "sample"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "fixture_validated"


def test_live_constructs_only_llm_metrics_with_fakes(monkeypatch, tmp_path: Path) -> None:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    question_types = sorted(APPROVED_QUESTION_TYPES)
    for index, record in enumerate(payload["records"]):
        record.update(
            question_text="Question",
            question_type=question_types[index % len(question_types)],
            topic="Topic",
            reference_answer="Answer",
            evidence={
                "document_id": "00000000-0000-0000-0000-000000000001",
                "chunk_id": "00000000-0000-0000-0000-000000000002",
                "document_title": "Title",
                "publication_year": 2024,
                "region": "DKI Jakarta",
                "page_start": 1,
                "page_end": 1,
                "source_url": "https://example.com/source.pdf",
                "excerpt": "Evidence",
            },
            verification_status="verified",
        )
    payload["dataset_status"] = "ready"
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    constructed: list[str] = []

    def metric(name):
        return type(name, (), {"__init__": lambda self, llm: constructed.append(name)})

    class FakeClient:
        def __init__(self, **kwargs):
            pass

    class FakeDataset:
        @classmethod
        def from_list(cls, samples):
            return samples

    class FakeResult:
        def to_pandas(self):
            return self

        def to_dict(self, orient):
            return [{"faithfulness": 1.0}]

    monkeypatch.setenv("RAGAS_LLM_API_KEY", "test")
    monkeypatch.setenv("RAGAS_LLM_MODEL", "configured-model")
    monkeypatch.setenv("RAGAS_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("RAGAS_LLM_PROVIDER", "configured-provider")
    monkeypatch.setattr(
        harness,
        "_load_ragas_components",
        lambda: (
            FakeClient,
            FakeDataset,
            lambda **kwargs: FakeResult(),
            lambda *args, **kwargs: object(),
            metric("Faithfulness"),
            metric("ContextPrecision"),
            metric("ContextRecall"),
        ),
    )

    result = harness.run_live(dataset_path, DEFAULT_FIXTURE_PATH)

    assert result["status"] == "completed"
    assert result["evaluation_label"] == "initial MVP baseline"
    assert constructed == ["Faithfulness", "ContextPrecision", "ContextRecall"]
