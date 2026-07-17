# Architecture Decisions

## Stripe and jobs seeds pinned for reproducible demo numbers

**Date**: 2026-07-16

All three data generators now use fixed seeds so `docker compose up` produces
identical numbers every run:

- Aria calls: seed 42 (unchanged -- already pinned)
- Stripe payments: seed 77 (new -- previously used global `random`)
- MongoDB jobs: seed 99 for job fields, derived from Aria seed 42 for
  `related_call_id` values (unchanged -- already pinned via
  `scripts/generate_job_seed.py`)

This makes the README transcripts, dashboard screenshots, and a fresh
`docker compose up` all show the same story. The only variation is
timestamps, which shift relative to `datetime.now()`.

## Observability behind compose profiles, instrumentation config-gated

**Date**: 2026-07-17

All observability services (Prometheus, Pushgateway, Grafana, Loki, Promtail)
run behind `profiles: [observability]` in docker-compose.yml. Plain
`docker compose up` starts exactly the same 6 services as before.

OpenTelemetry instrumentation is gated on `OTEL_ENABLED=true`. When unset or
false, no OTel packages are imported at runtime and no metrics are emitted.
The `make observability` target sets this variable and activates the profile
in a single command.

Pipeline metrics are pushed to a Prometheus Pushgateway (the standard pattern
for batch jobs). The push is non-fatal: if the Pushgateway is unreachable,
the pipeline logs a warning and succeeds normally.

dbt test results are parsed from `target/run_results.json` (dbt's structured
artifact), not from stdout scraping.

Setuptools is pinned to <81 in the API Dockerfile because the OTel FastAPI
instrumentor depends on `pkg_resources`, which was removed in setuptools 81+.
