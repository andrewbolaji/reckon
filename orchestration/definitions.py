"""The Reckon code location.

Load target for everything: ``dagster dev``, ``dagster job execute``,
``dagster asset materialize``, and the ``dagster definitions validate`` gate in
CI all point at this module.
"""

from dagster import Definitions

from orchestration.assets_dbt import reckon_dbt_assets
from orchestration.assets_ingest import ingest_assets
from orchestration.jobs import all_jobs
from orchestration.resources import dbt_resource
from orchestration.schedules import all_schedules
from orchestration.sensors import all_sensors

defs = Definitions(
    assets=[*ingest_assets, reckon_dbt_assets],
    jobs=all_jobs,
    schedules=all_schedules,
    sensors=all_sensors,
    resources={"dbt": dbt_resource},
)
