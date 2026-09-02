#!/usr/bin/env python3
"""Write a concise, truthful summary from retrieval, response, and RAGAS reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", type=Path, default=EVALUATIONS_DIR / "retrieval_diagnostic_1000.json")
    parser.add_argument("--responses", type=Path, default=EVALUATIONS_DIR / "response_generation_report.json")
    parser.add_argument("--ragas", type=Path, default=EVALUATIONS_DIR / "ragas_report.json")
    parser.add_argument("--output", type=Path, default=EVALUATIONS_DIR / "metrics_summary.md")
    args = parser.parse_args()
    retrieval = json.loads(args.retrieval.read_text(encoding="utf-8"))
    responses = json.loads(args.responses.read_text(encoding="utf-8"))
    ragas = json.loads(args.ragas.read_text(encoding="utf-8"))
    lines = [
        "# T-EVAL-0003 Metrics Summary",
        "",
        f"- Retrieval status: `{retrieval.get('status')}`",
        f"- Retrieval sample count: `{retrieval.get('dataset_capacity')}`",
        f"- Retrieval failures: `{retrieval.get('metrics', {}).get('total_failures')}`",
        f"- Response generation status: `{responses.get('status')}`",
        f"- Response count: `{responses.get('response_count')}`",
        f"- Response failures: `{responses.get('failure_count')}`",
        f"- RAGAS status: `{ragas.get('status')}`",
        f"- RAGAS sample count: `{ragas.get('sample_count')}`",
        "",
        "## Retrieval Overall",
        "",
        "```json",
        json.dumps(retrieval.get("metrics", {}).get("overall", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## RAGAS",
        "",
        "```json",
        json.dumps(ragas.get("metrics"), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "Automated metrics are baseline evidence only and do not establish comprehensive system accuracy.",
    ]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "written", "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
