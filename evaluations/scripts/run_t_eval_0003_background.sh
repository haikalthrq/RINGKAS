#!/usr/bin/env bash
set -u

ROOT="${RINGKAS_ROOT:-/home/haikalthoriqa/RINGKAS}"
cd "$ROOT" || exit 1

if [ ! -f "$ROOT/.env" ]; then
  exit 1
fi

started_at="$(date +%s)"
docker compose --env-file .env -f infra/docker-compose.yml run -d --rm --no-deps --user 0:0 \
  --env RINGKAS_ENV_FILE=/run/ringkas.env --env PYTHONPATH=/workspace/services/rag-worker \
  --volume "$ROOT:/workspace:ro" --volume "$ROOT/evaluations:/evaluation:rw" \
  --volume "$ROOT/.env:/run/ringkas.env:ro" --entrypoint python rag-query \
  /evaluation/scripts/generate_factual_responses.py \
  --dataset /evaluation/evaluation_dataset.json --output /evaluation/responses.json \
  --checkpoint /evaluation/responses_checkpoint.json \
  --report /evaluation/response_generation_report.json \
  --log /evaluation/response_generation.log \
  --retrieval-endpoint http://rag-query:8081/retrieve >/dev/null

while true; do
  report_ready="$(python3 -c 'import sys; from pathlib import Path; p=Path(sys.argv[1]); print(int(p.stat().st_mtime) > int(sys.argv[2])) if p.exists() else print(False)' evaluations/response_generation_report.json "$started_at")"
  status="$(python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); print(json.loads(p.read_text()).get("status", "")) if p.exists() else print("")' evaluations/response_generation_report.json)"
  if [ "$report_ready" = "True" ] && { [ "$status" = "completed" ] || [ "$status" = "blocked" ]; }; then
    break
  fi
  sleep 30
done

if [ "$status" = "completed" ]; then
  docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps --user 0:0 \
    --volume "$ROOT:/workspace:ro" --volume "$ROOT/evaluations:/evaluation:rw" \
    --entrypoint python rag-query /evaluation/scripts/write_automated_audit.py \
    --dataset /evaluation/evaluation_dataset.json --responses /evaluation/responses.json \
    --output /evaluation/automated_audit_report.csv

  docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps --user 0:0 \
    --env PYTHONPATH=/workspace/services/rag-worker --volume "$ROOT:/workspace:ro" \
    --volume "$ROOT/evaluations:/evaluation:rw" --volume "$ROOT/.env:/run/ringkas.env:ro" \
    --entrypoint sh rag-query -c 'set -a; . /run/ringkas.env; set +a; python -m pip install --quiet ragas==0.4.3 langchain-community==0.3.31 langchain-openai==1.3.5 openai==2.46.0; python /evaluation/scripts/run_live_ragas_1000.py --dataset /evaluation/evaluation_dataset.json --responses /evaluation/responses.json --output /evaluation/ragas_report.json'
else
  python3 -c 'import json; from pathlib import Path; Path("evaluations/ragas_report.json").write_text(json.dumps({"evaluation_label":"live RAGAS evaluation","status":"blocked","sample_count":0,"metrics":None,"error_class":"ResponseValidationError","reason":"response generation did not complete; no synthetic responses were evaluated"}, indent=2)+"\n")'
fi

docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps --user 0:0 \
  --volume "$ROOT:/workspace:ro" --volume "$ROOT/evaluations:/evaluation:rw" \
  --entrypoint python rag-query /evaluation/scripts/write_metrics_summary.py \
  --retrieval /evaluation/retrieval_diagnostic_1000.json \
  --responses /evaluation/response_generation_report.json \
  --ragas /evaluation/ragas_report.json --output /evaluation/metrics_summary.md
