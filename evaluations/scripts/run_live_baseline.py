"""Runner script for live RAGAS baseline with atomic checkpointing and auto-save of report."""
import json
import pathlib
import sys
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from ringkas_worker.ragas_harness import run_live

DATASET_PATH = ROOT / "evaluations" / "evaluation_dataset.json"
RESPONSES_PATH = ROOT / "evaluations" / "responses.json"
REPORT_PATH = ROOT / "evaluations" / "ragas_report.json"

print(f"[RAGAS] Starting live evaluation baseline...", file=sys.stderr)
print(f"[RAGAS] Dataset: {DATASET_PATH}", file=sys.stderr)
print(f"[RAGAS] Responses: {RESPONSES_PATH}", file=sys.stderr)

result = run_live(DATASET_PATH, RESPONSES_PATH)

print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

if result.get("status") == "completed":
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[RAGAS] Successfully completed 100 samples and wrote {REPORT_PATH}", file=sys.stderr)
    sys.exit(0)
elif result.get("status") == "blocked":
    print(f"[RAGAS] Evaluation blocked: {result.get('reason')} (completed {result.get('completed_finite_metrics', 0)} metrics)", file=sys.stderr)
    sys.exit(2)
else:
    print(f"[RAGAS] Status: {result.get('status')}", file=sys.stderr)
    sys.exit(0)
