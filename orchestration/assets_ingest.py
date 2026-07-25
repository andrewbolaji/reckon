"""The three source ingestions, as date-partitioned assets.

Each asset owns one source end to end: extract to the lake, then load that same
window into the warehouse's raw schema. Keeping extract and load in one asset is
deliberate. Splitting them would put an asset boundary in the middle of a single
idempotent unit of work, and a retry would then have to reason about which half
already ran.

Partitions are what make a backfill real. Each run deletes and reinserts only
the days in its window (``ingest/loader.py``), so refilling a missed week leaves
every other week standing.
"""

import os
from dataclasses import dataclass
from typing import Callable

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetsDefinition,
    Backoff,
    BackfillPolicy,
    Jitter,
    MaterializeResult,
    MetadataValue,
    RetryPolicy,
    asset,
)

from ingest.config import LakeConfig, MongoConfig, WarehouseConfig
from ingest.extractors import aria_calls, mongo_jobs, stripe_payments
from ingest.loader import load_to_warehouse
from ingest.pipeline import CALL_COLUMNS, JOB_COLUMNS, PAYMENT_COLUMNS
from ingest.window import DateWindow
from orchestration.partitions import daily_partitions

INGEST_GROUP = "ingest"

# Three attempts after the first, backing off 2s, 4s, 8s. Sources fail for
# boring transient reasons (a rate limit, a Mongo election, a dropped
# connection), and the jitter keeps three assets that failed together from
# retrying in lockstep.
INGEST_RETRY_POLICY = RetryPolicy(
    max_retries=3,
    delay=2,
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.PLUS_MINUS,
)

# Fault injection for the README demo. Comma-separated asset names, e.g.
# RECKON_BREAK_SOURCE=stripe_payments_raw. It lives here rather than in ingest/
# so nothing in the production extract path knows this exists.
BREAK_ENV_VAR = "RECKON_BREAK_SOURCE"


@dataclass(frozen=True)
class SourceSpec:
    """Everything that differs between the three otherwise identical assets."""

    asset_name: str
    lake_source: str  # the source's directory in the lake
    raw_table: str  # its table in the warehouse "raw" schema
    columns: list[str]
    date_column: str  # the column a windowed load deletes on
    description: str
    extract: Callable[[LakeConfig, DateWindow], str]


SOURCE_SPECS = [
    SourceSpec(
        asset_name="aria_calls_raw",
        lake_source="aria_calls",
        raw_table="aria_calls",
        columns=CALL_COLUMNS,
        date_column="timestamp",
        description="Aria voice-agent call records, landed in the lake and loaded to raw.",
        extract=lambda lake, window: aria_calls.extract(lake, window=window),
    ),
    SourceSpec(
        asset_name="stripe_payments_raw",
        lake_source="stripe_payments",
        raw_table="stripe_payments",
        columns=PAYMENT_COLUMNS,
        date_column="timestamp",
        description="Stripe payment transactions, landed in the lake and loaded to raw.",
        extract=lambda lake, window: stripe_payments.extract(lake, window=window),
    ),
    SourceSpec(
        asset_name="mongo_jobs_raw",
        lake_source="mongo_jobs",
        raw_table="jobs",
        columns=JOB_COLUMNS,
        date_column="scheduled_at",
        description="MongoDB service jobs, landed in the lake and loaded to raw.",
        extract=lambda lake, window: mongo_jobs.extract(
            lake, MongoConfig.from_env(), window=window
        ),
    ),
]

# dbt declares these same three tables as sources. Mapping them onto the ingest
# asset keys is what fuses ingestion and transformation into one graph, so a
# failed extract halts its own downstream models instead of letting dbt rebuild
# marts on stale raw data. See orchestration/assets_dbt.py.
DBT_SOURCE_TO_ASSET_KEY = {
    spec.raw_table: AssetKey(spec.asset_name) for spec in SOURCE_SPECS
}


def broken_sources() -> set[str]:
    """Asset names the operator has asked to fail, from the environment."""
    raw = os.getenv(BREAK_ENV_VAR, "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _fail_if_broken(asset_name: str) -> None:
    if asset_name in broken_sources():
        raise RuntimeError(
            f"{asset_name}: source unavailable (simulated by {BREAK_ENV_VAR}). "
            "Downstream models will not run against stale data."
        )


def build_ingest_asset(
    spec: SourceSpec, retry_policy: RetryPolicy | None = INGEST_RETRY_POLICY
) -> AssetsDefinition:
    """Build one source asset. The three differ only by their SourceSpec.

    ``retry_policy`` is a parameter so tests can build a no-retry copy; waiting
    out an exponential backoff to watch a failure fail is not a useful test.
    """

    @asset(
        name=spec.asset_name,
        description=spec.description,
        group_name=INGEST_GROUP,
        partitions_def=daily_partitions,
        # One run per window rather than one run per day. This is what lets
        # `dagster asset materialize --partition-range` refill a whole missed
        # week in a single command, and it means the extractor generates its
        # deterministic set once instead of once per day.
        backfill_policy=BackfillPolicy.single_run(),
        retry_policy=retry_policy,
        kinds={"python"},
    )
    def _ingest_asset(context: AssetExecutionContext) -> MaterializeResult:
        time_window = context.partition_time_window
        window = DateWindow.from_time_window(time_window.start, time_window.end)
        context.log.info(f"{spec.asset_name}: ingesting {window}")

        _fail_if_broken(spec.asset_name)

        lake = LakeConfig.from_env()
        warehouse = WarehouseConfig.from_env()

        spec.extract(lake, window)
        rows = load_to_warehouse(
            lake,
            warehouse,
            spec.lake_source,
            spec.raw_table,
            spec.columns,
            window=window,
            date_column=spec.date_column,
        )

        return MaterializeResult(
            metadata={
                "rows_loaded": MetadataValue.int(rows),
                "window": MetadataValue.text(str(window)),
                "days": MetadataValue.int(len(window.days())),
                "raw_table": MetadataValue.text(f'"raw".{spec.raw_table}'),
            }
        )

    return _ingest_asset


ingest_assets = [build_ingest_asset(spec) for spec in SOURCE_SPECS]
