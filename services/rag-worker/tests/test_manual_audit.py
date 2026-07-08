import csv
from pathlib import Path

from ringkas_worker.manual_audit import REQUIRED_COLUMNS, validate_audit_template


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "manual_audit_template.csv"


def test_manual_audit_template_has_exactly_20_pending_rows() -> None:
    rows = validate_audit_template(TEMPLATE_PATH)

    assert len(rows) == 20
    assert tuple(rows[0]) == REQUIRED_COLUMNS
    assert rows[-1]["question_id"] == "q-020"
    assert all(row["audit_status"] == "pending" for row in rows)


def test_manual_audit_accepts_any_20_unique_dataset_ids(tmp_path: Path) -> None:
    path = tmp_path / "audit.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for index in range(81, 101):
            writer.writerow({"question_id": f"q-{index:03d}", "audit_status": "pending"})

    rows = validate_audit_template(path)

    assert rows[0]["question_id"] == "q-081"
    assert rows[-1]["question_id"] == "q-100"
