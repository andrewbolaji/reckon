#!/usr/bin/env bash
# One full pipeline run, executed through Dagster.
#
# This is the non-daemon path: the docker compose one-shot that seeds the
# warehouse before the API and Metabase start, and the Kubernetes CronJob that
# triggers runs on the cluster. Both execute the same `reckon_full_refresh` job
# the schedule runs, against the same asset definitions, so retries, lineage,
# and the dbt trust gate behave identically wherever a run is triggered from.
#
# Scheduling itself now belongs to Dagster (orchestration/schedules.py). What is
# left here is a trigger and the metrics push, because with no daemon watching,
# no sensor fires and nothing would otherwise reach Prometheus.
set -euo pipefail

DBT_TARGET="${DBT_TARGET:-dev}"
DAGSTER_MODULE="orchestration.definitions"
JOB="reckon_full_refresh"

cd /app

# The window to materialise. Defaults to the whole demo window so a first boot
# fills the warehouse exactly as the old full-refresh script did.
read -r WINDOW_START WINDOW_END <<<"$(python -c "
from orchestration.partitions import full_window
print('%s %s' % full_window())
")"
PARTITION_START="${PIPELINE_WINDOW_START:-$WINDOW_START}"
PARTITION_END="${PIPELINE_WINDOW_END:-$WINDOW_END}"

echo "=== Reckon Pipeline (dbt target: ${DBT_TARGET}, window: ${PARTITION_START}..${PARTITION_END}) ==="
echo ""

START_TIME=$SECONDS

# The ingest assets carry BackfillPolicy.single_run(), so the whole window runs
# as one run rather than one run per day, and the dbt models build once after it.
set +e
dagster job execute \
    -m "${DAGSTER_MODULE}" \
    -j "${JOB}" \
    --tags "{\"dagster/asset_partition_range_start\": \"${PARTITION_START}\", \"dagster/asset_partition_range_end\": \"${PARTITION_END}\"}"
RUN_STATUS=$?
set -e

DURATION=$(( SECONDS - START_TIME ))

# Report the outcome to the Pushgateway. Non-fatal by design: observability
# being unavailable must never change whether the pipeline succeeded.
if [ "${RUN_STATUS}" -eq 0 ]; then
    echo ""
    echo "=== Pipeline complete (${DURATION}s) ==="
    python -m orchestration.report_run --status success --duration "${DURATION}" \
        || echo "[telemetry] Success report failed (non-fatal), continuing."
else
    echo ""
    echo "=== Pipeline FAILED (exit ${RUN_STATUS}) ===" >&2
    python -m orchestration.report_run --status failure \
        --reason "${JOB} failed (exit ${RUN_STATUS}) for window ${PARTITION_START}..${PARTITION_END}" \
        || echo "[telemetry] Failure report failed (non-fatal), continuing." >&2
fi

exit "${RUN_STATUS}"
