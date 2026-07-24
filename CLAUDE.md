# Reckon

## What this is
Reckon is a self-contained BI platform for a home-services business: a Python pipeline ingests Aria voice-agent call records, Stripe payments, and MongoDB service jobs, loads them to a Postgres or Redshift warehouse, and dbt transforms them into three marts. A FastAPI plus React dashboard and Metabase serve the data, and an MCP copilot answers plain-English questions grounded strictly in those marts.

## First 10 minutes
Needs Python 3.12 (the version CI uses), Node 20, and Docker. Every command here was run on a clean checkout before it was written down.

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
- `ingest/` extracts sources (`pipeline.py`), writes the lake (`lake.py`), loads raw (`loader.py`).
- `transform/` is the dbt project: `models/staging` typed views, `models/marts` tables, trust gate in the tests.
- `api/` (FastAPI `main.py`) serves marts; `dashboard/` (React, Vite) and Metabase render them.
- `copilot/` is the MCP server and CLI; safety lives in the tools and DB role, not the prompt.
- `infra/` (terraform, helm, docker) and `observability/` are the cloud and monitoring layers.

## Gotchas
- Bare `python` does not exist here, and psycopg2 has no wheel on 3.14. Activate `.venv` (3.12) or `make test` and dbt fail.
- Local warehouse is Postgres, prod is Redshift. `raw` is a Redshift reserved word, so the schema is always double-quoted `"raw"` (`ingest/loader.py`, `transform/models/staging/sources.yml`). No `FILTER (WHERE)` and no `now()` default: both fail on Redshift.
- Demo data is deterministic, anchored to `REFERENCE_DATE` with seed 42. The loader stores every raw column as text, so type bugs surface in dbt staging, not ingest.
- Compose order matters: the pipeline is a run-once job and api and metabase wait for it, so first boot is slow while it seeds.
- Copilot never trusts the prompt for safety: read-only `reckon_reader` role, SQL validator, row cap, statement timeout, and a stale-data refusal past 48 hours.

## Definition of done
- Plan approved before non-trivial code.
- Tests pass, and the new behavior (including its failure mode) has a test.
- Static check clean: `dbt parse` for model changes. This repo has no linter or typechecker, so tests and `dbt parse` are the gates.
- Diff self-reviewed. UI changes verified by a screenshot from `make local`.
- Committed and pushed. Uncommitted work does not exist.

## House style
No em dashes anywhere, in any file and in commit messages (subject and body). Use commas, periods, or parentheses. Headings are sentence case.
