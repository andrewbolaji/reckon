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
