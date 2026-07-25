"""The two jobs: the whole DAG, and ingest alone for backfills."""

from dagster import AssetSelection, define_asset_job

from orchestration.assets_ingest import SOURCE_SPECS

INGEST_SELECTION = AssetSelection.assets(*[spec.asset_name for spec in SOURCE_SPECS])

# Everything: the three ingestions, every dbt model, and the dbt tests that ride
# with them. Mixing the partitioned ingest assets with the unpartitioned dbt
# assets is fine; the job takes the daily partitions and the dbt models run once
# per run, after their sources.
reckon_full_refresh = define_asset_job(
    name="reckon_full_refresh",
    description="Ingest all three sources for a window, then build every dbt model.",
    selection=AssetSelection.all(),
)

# Ingest only, for refilling days without rebuilding marts in the same run. The
# marts can then be rebuilt once at the end rather than once per backfilled day.
reckon_ingest_backfill = define_asset_job(
    name="reckon_ingest_backfill",
    description="Re-ingest a date window across all three sources.",
    selection=INGEST_SELECTION,
)

all_jobs = [reckon_full_refresh, reckon_ingest_backfill]
