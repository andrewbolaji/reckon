"""Report a run outcome to the Pushgateway from the CLI path.

The sensors in ``orchestration/sensors.py`` cover runs that go through the
Dagster daemon. This module covers the other path: ``scripts/run_pipeline.sh``,
which the compose one-shot and the Kubernetes CronJob use to execute the job
directly with no daemon watching. Without this, a cluster run would materialise
assets and never tell Prometheus anything.

Row counts come from the warehouse here rather than from materialisation
metadata, because a CLI run may use ephemeral storage and leave no event log
behind once the process exits.

Usage:
    python -m orchestration.report_run --status success --duration 42
    python -m orchestration.report_run --status failure --reason "..."
"""

import argparse
import sys

import psycopg2

from ingest.config import WarehouseConfig
from ingest.telemetry import push_run_failure, push_run_success
from orchestration.assets_ingest import SOURCE_SPECS
from orchestration.resources import DBT_RUN_RESULTS

# "raw" is quoted because it is a Redshift reserved word, the same reason
# ingest/loader.py quotes it.
_RAW = '"raw"'


def rows_by_source() -> dict[str, int]:
    """Count the rows currently in each raw table.

    Non-fatal: reporting is never worth failing a run that already succeeded.
    """
    counts: dict[str, int] = {}
    try:
        wh = WarehouseConfig.from_env()
        conn = psycopg2.connect(wh.connection_string)
        try:
            cur = conn.cursor()
            for spec in SOURCE_SPECS:
                cur.execute(f"SELECT count(*) FROM {_RAW}.{spec.raw_table}")
                counts[spec.raw_table] = cur.fetchone()[0]
            cur.close()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[report_run] Could not read row counts (non-fatal): {e}")
    return counts


def _dbt_results_path() -> str | None:
    return str(DBT_RUN_RESULTS) if DBT_RUN_RESULTS.exists() else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", choices=["success", "failure"], required=True)
    parser.add_argument(
        "--duration", type=float, default=0.0, help="Run duration in seconds."
    )
    parser.add_argument(
        "--reason", default="pipeline run failed", help="Why the run failed."
    )
    args = parser.parse_args(argv)

    if args.status == "success":
        push_run_success(
            duration_seconds=args.duration,
            rows_by_source=rows_by_source(),
            dbt_results_path=_dbt_results_path(),
        )
    else:
        push_run_failure(args.reason, dbt_results_path=_dbt_results_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
