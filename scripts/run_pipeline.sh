#!/usr/bin/env bash
set -euo pipefail

DBT_TARGET="${DBT_TARGET:-dev}"

echo "=== Reckon Pipeline (target: ${DBT_TARGET}) ==="
echo ""

echo "[Step 1] Running ingestion (extract + load)..."
cd /app
python -m ingest.pipeline

echo ""
echo "[Step 2] Running dbt transforms..."
cd /app/transform
dbt deps --profiles-dir .
dbt build --profiles-dir . --target "${DBT_TARGET}" --full-refresh

echo ""
echo "=== Pipeline complete ==="

# Push metrics to Pushgateway if OTEL_ENABLED=true.
# Non-fatal: the pipeline has already succeeded at this point.
if [ "${OTEL_ENABLED:-false}" = "true" ]; then
    echo ""
    echo "[Step 3] Pushing metrics to Pushgateway..."
    cd /app
    python -c "
from ingest.telemetry import push_pipeline_metrics
from ingest.pipeline import run as _  # noqa: already ran above
import json, pathlib

# Re-read the row counts from the raw tables (fast, just counts)
import psycopg2, os
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', 'warehouse'),
    port=os.getenv('POSTGRES_PORT', '5432'),
    dbname=os.getenv('POSTGRES_DB', 'reckon'),
    user=os.getenv('POSTGRES_USER', 'reckon'),
    password=os.getenv('POSTGRES_PASSWORD', 'reckon_dev'),
)
cur = conn.cursor()
rows = {}
for table, key in [('aria_calls', 'aria_calls'), ('stripe_payments', 'stripe_payments'), ('jobs', 'jobs')]:
    cur.execute(f'SELECT count(*) FROM \"raw\".{table}')  # \"raw\" quoted: reserved word on Redshift
    rows[key] = cur.fetchone()[0]
cur.close()
conn.close()

# Parse dbt run_results.json for test counts
dbt_path = '/app/transform/target/run_results.json'

# Duration: use a rough estimate from the dbt artifact elapsed_time
try:
    data = json.loads(pathlib.Path(dbt_path).read_text())
    duration = data.get('elapsed_time', 0)
except Exception:
    duration = 0

push_pipeline_metrics(duration, rows, dbt_path)
" || echo "[telemetry] Metrics push failed (non-fatal), continuing."
fi
