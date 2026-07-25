"""Every dbt model as an asset, loaded from the project's own manifest.

Nothing here lists models by hand. dagster-dbt reads ``transform/``'s manifest,
so adding a model to the dbt project adds a node to this graph with no change in
orchestration, and the dbt tests run inline exactly as ``dbt build`` runs them.

The translator does the two pieces of wiring that make this one system rather
than two:

1. dbt's sources are mapped onto the ingest asset keys, so the raw tables are
   the same nodes ingestion produces.
2. The marts carry a freshness policy matching the trust gate, so Dagster's idea
   of stale and the copilot's idea of stale cannot drift apart.
"""

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from dagster import AssetExecutionContext, AssetKey, AssetSpec, FreshnessPolicy
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

from orchestration.assets_ingest import DBT_SOURCE_TO_ASSET_KEY
from orchestration.resources import dbt_project

# The same thresholds the copilot's trust gate enforces
# (copilot/trust_gate.py) and dbt's own source freshness config
# (transform/models/staging/sources.yml): warn at 24 hours, fail at 48.
FRESHNESS_WARN_HOURS = 24
FRESHNESS_FAIL_HOURS = 48

MART_FRESHNESS_POLICY = FreshnessPolicy.time_window(
    fail_window=timedelta(hours=FRESHNESS_FAIL_HOURS),
    warn_window=timedelta(hours=FRESHNESS_WARN_HOURS),
)

MARTS_GROUP = "marts"
STAGING_GROUP = "staging"

# dagster-dbt writes artifacts to a fresh directory per invocation by default,
# which is the right call when runs can overlap. Reckon pins it to the project's
# own target/ so run_results.json lands where the metrics push looks for it
# (orchestration/report_run.py, orchestration/sensors.py). Without this, dbt
# test counts always report zero and PipelineDbtTestFailure could never fire.
# Safe because the instance runs one pipeline run at a time
# (infra/docker/dagster.yaml sets max_concurrent_runs: 1).
DBT_TARGET_PATH = Path("target")


def _is_mart(dbt_resource_props: Mapping[str, Any]) -> bool:
    """True for models materialised into the marts schema.

    Keyed on the model's directory rather than a name prefix, because the
    directory is what dbt_project.yml already uses to decide schema and
    materialisation.
    """
    return "marts" in dbt_resource_props.get("fqn", [])


class ReckonDbtTranslator(DagsterDbtTranslator):
    """Maps dbt nodes onto Reckon's asset keys, groups, and freshness policies."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        """Point dbt's sources at the assets that actually produce them.

        Without this the dbt sources would be their own disconnected nodes and a
        failed extract would leave the marts happily rebuilding on stale raw
        data, which is the exact failure this phase exists to make visible.
        """
        if dbt_resource_props["resource_type"] == "source":
            mapped = DBT_SOURCE_TO_ASSET_KEY.get(dbt_resource_props["name"])
            if mapped is not None:
                return mapped
        return super().get_asset_key(dbt_resource_props)

    def get_asset_spec(self, manifest, unique_id, project) -> AssetSpec:
        spec = super().get_asset_spec(manifest, unique_id, project)
        props = manifest["nodes"].get(unique_id) or manifest["sources"].get(unique_id)
        if props is None:
            return spec
        if _is_mart(props):
            return spec.replace_attributes(
                freshness_policy=MART_FRESHNESS_POLICY,
                group_name=MARTS_GROUP,
            )
        if "staging" in props.get("fqn", []):
            return spec.replace_attributes(group_name=STAGING_GROUP)
        return spec


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=ReckonDbtTranslator(),
)
def reckon_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Build the selected dbt models, running their tests inline.

    ``dbt build`` rather than ``dbt run``: the trust gate is the tests, and a
    failing test must stop downstream models from materialising. Splitting run
    and test would let a mart land before its own test had a chance to reject it.
    """
    yield from dbt.cli(
        ["build"], context=context, target_path=DBT_TARGET_PATH
    ).stream()
