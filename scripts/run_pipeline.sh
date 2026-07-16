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
