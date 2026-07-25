"""Shared resources and paths for the Dagster code location."""

import sys
from pathlib import Path

from dagster_dbt import DbtCliResource, DbtProject

# orchestration/ sits next to transform/ and ingest/ both in the repo and in the
# pipeline image (/app), so one relative resolution covers every environment.
REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = REPO_ROOT / "transform"

# profiles.yml lives inside the dbt project and is env-var driven, so the same
# definitions load against local Postgres or Redshift with no code change.
dbt_project = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROJECT_DIR,
)


def _dbt_executable() -> str:
    """Locate dbt, preferring the one installed beside this interpreter.

    The repo's dbt lives in .venv, and CLAUDE.md's first gotcha is that bare
    `python` is not the right one here. Resolving dbt relative to
    ``sys.executable`` means `.venv/bin/dagster` and `.venv/bin/python -m ...`
    work whether or not the venv is on PATH, while the Docker image and CI,
    where dbt is a plain PATH entry, are unaffected.
    """
    beside_interpreter = Path(sys.executable).parent / "dbt"
    return str(beside_interpreter) if beside_interpreter.exists() else "dbt"


# Builds the manifest on the fly under `dagster dev` so the asset graph is never
# stale while iterating on models. In CI and in the image the manifest is built
# ahead of time by `dbt parse`. Failing to prepare is not fatal on its own: if a
# manifest is already on disk the code location still loads, and if one is not,
# the import below raises with a far clearer message than a subprocess error.
try:
    dbt_project.prepare_if_dev()
except Exception as e:  # noqa: BLE001
    print(f"[orchestration] dbt parse skipped ({e}); using the manifest on disk.")

dbt_resource = DbtCliResource(
    project_dir=dbt_project, dbt_executable=_dbt_executable()
)

# dbt writes run_results.json here. The failure sensor reads it to report real
# test counts rather than guessing why a run went red.
DBT_RUN_RESULTS = DBT_PROJECT_DIR / "target" / "run_results.json"
