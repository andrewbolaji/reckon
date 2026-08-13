# Reckon

## What this is
Reckon is a self-contained BI platform for a home-services business: a Python pipeline ingests Aria voice-agent call records, Stripe payments, and MongoDB service jobs, loads them to a Postgres or Redshift warehouse, and dbt transforms them into three marts. A FastAPI plus React dashboard and Metabase serve the data, and an MCP copilot answers plain-English questions grounded strictly in those marts.

## First 10 minutes
Needs Python 3.12 (the version CI uses), Node 24 LTS, and Docker. Every command here was run on a clean checkout before it was written down.

```bash
# Python unit tests (ingest)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r ingest/requirements-dev.txt
make test                        # pytest ingest/tests, database free

# Copilot safety tests (no database needed)
pip install -r copilot/requirements.txt
pytest copilot/tests/test_security.py::TestSqlInjection copilot/tests/test_trust_gate.py::TestSqlValidation -q

# Dashboard tests
cd dashboard && npm ci && npm test && cd ..

# See it working: build and run the whole stack
make local                       # docker compose up --build
# dashboard http://localhost:5173, api http://localhost:8000/health
make local-down
```

## Architecture map
- `ingest/` extracts sources (`pipeline.py`), writes the lake (`lake.py`), loads raw (`loader.py`). Window-aware: every function takes an optional `window: DateWindow` so a backfill refills a date range instead of doing a full refresh.
- `transform/` is the dbt project: `models/staging` typed views, `models/marts` tables, trust gate in the tests.
- `orchestration/` is the Dagster project: the three ingestions and every dbt model as software-defined assets in one graph (`assets_ingest.py`, `assets_dbt.py`), a daily schedule, and run-outcome sensors that push into the existing Pushgateway (`sensors.py`).
- `api/` (FastAPI `main.py`) serves marts; `dashboard/` (React, Vite) and Metabase render them.
- `copilot/` is the MCP server and CLI; safety lives in the tools and DB role, not the prompt.
- `infra/` (terraform, helm, docker) and `observability/` are the cloud and monitoring layers.

## Gotchas
- Bare `python` does not exist here, and psycopg2 has no wheel on 3.14. Use `.venv` (3.12); Make targets select its executables without requiring activation.
- Local warehouse is Postgres, prod is Redshift. `raw` is a Redshift reserved word, so the schema is always double-quoted `"raw"` (`ingest/loader.py`, `transform/models/staging/sources.yml`). No `FILTER (WHERE)` and no `now()` default: both fail on Redshift.
- Demo data is deterministic, anchored to `REFERENCE_DATE` with seed 42. The loader stores every raw column as text, so type bugs surface in dbt staging, not ingest. The ingest window starts 31 days back, not 30: the extractors' intraday offset can push the earliest record a day earlier than a naive 30-day window, and a full run would silently drop it.
- Compose order matters: the pipeline is a run-once job and api and metabase wait for it, so first boot is slow while it seeds.
- Copilot never trusts the prompt for safety: read-only `reckon_reader` role, SQL validator, row cap, statement timeout, and a stale-data refusal past 48 hours.
- `dagster-dbt` hard-pins its own dagster version, so `orchestration/requirements.txt` is installed in its own CI job, never alongside the copilot or API dependency sets. `dbt parse` has to run before `dagster definitions validate`: the code location loads the dbt asset graph from the manifest, not from a live warehouse connection.
- `dagster`'s `Jitter` enum only has `FULL` and `PLUS_MINUS`. There is no `Jitter.PLUS`.
- The webserver and daemon load `orchestration/` from one persistent `dagster-code-server` container via `workspace.yaml`, not each from their own `-m orchestration.definitions` subprocess. A module-loaded subprocess is ephemeral and cycles on an idle heartbeat, and a sensor tick landing on a subprocess mid-restart silently does nothing instead of failing loud, so `dagster-webserver`/`dagster-daemon` must wait on the code server's real gRPC health check, not just its container start.
- Both run-outcome sensors and the daily schedule need `default_status=DefaultSensorStatus.RUNNING` (schedules: `DefaultScheduleStatus.RUNNING`), and the sensors also need `monitor_all_code_locations=True`. Dagster's defaults are stopped, and unset, until someone opts in, so without these a run's failure never reaches the Pushgateway and nothing says why.

## Definition of done
- Plan approved before non-trivial code.
- Tests pass, and the new behavior (including its failure mode) has a test.
- Static check clean: `dbt parse` for model changes. This repo has no linter or typechecker, so tests and `dbt parse` are the gates.
- Diff self-reviewed. UI changes verified by a screenshot from `make local`.
- Committed and pushed. Uncommitted work does not exist.

## House style
No em dashes anywhere, in any file and in commit messages (subject and body). Use commas, periods, or parentheses. Headings are sentence case.
