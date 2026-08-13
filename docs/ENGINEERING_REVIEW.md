# Reckon engineering review

Scope: the auth and access-control story (and what "production" actually
means here, since Reckon has no Supabase-style test/live split), which AWS
target a deployment points at, the closest things this repo has to a Stripe
webhook and a Resend integration, how the five test suites and CI actually
work, and every place a doc in this repo says something the code does not
do. Findings are cited as `path:line`. No secrets, key material, or project
identifiers beyond what `infra/terraform/variables.tf` already publishes
(the AWS account is not in this repo; the region default is `us-east-1` and
the resource prefix is `reckon`) appear below.

## Running this review

**Prerequisites:** Python 3.12, Node 20, Docker and Docker Compose. That is
the whole requirement for the local path (`CLAUDE.md:7`). Python deps
install per-package (`ingest/requirements-dev.txt`, `copilot/requirements.txt`,
`api/requirements.txt`), not from one root file; there is no root
`pyproject.toml` or `.python-version`, so the version pin lives only in
`CLAUDE.md:7` and `.github/workflows/ci.yml:18`. Node deps are `npm ci`
inside `dashboard/`.

**Keys a reviewer will not have, and what needs them:**

- `ANTHROPIC_API_KEY` (`.env.example:37`), only for the MCP copilot's live
  Claude calls. Without it, every copilot test that does not touch the
  network still runs; only `python -m copilot.cli` and MCP-server usage need
  it.
- AWS credentials, only for anything under `infra/terraform/` and the
  `make infra` / `make up` / `make helm-install` Makefile targets. Nothing
  else in the repo needs AWS.
- There is no Stripe key anywhere to obtain. See "Stripe" below; the
  extractor never calls a real API.
- There is no Supabase, Resend, or any user-facing signup/login system in
  this repo. See "What 'auth' means here" below for the closest analogues.

**What cannot be exercised without credentials:**

- Anything past `make infra` (Terraform apply, EKS, Redshift Serverless,
  `make helm-install`, `make monitoring`) needs an AWS account and costs
  money while running (`README.md:226`, "~$3-5" for a full stack-hour).
- The live Claude round-trip in the copilot (`python -m copilot.cli`,
  the MCP server) needs `ANTHROPIC_API_KEY`.
- Everything else, including the full local stack (`make local`), all five
  test suites, and the CI pipeline, needs only Docker and runs with no
  external credentials at all. The copilot's DB-backed tests specifically
  skip themselves (not fail) when Postgres is unreachable
  (`copilot/tests/conftest.py:24-27`), so a reviewer who never runs
  `make local` still gets a passing `pytest`, just a shorter one.

## What "auth," "test vs. live," and "which project" mean for Reckon

Reckon has no user accounts, no login, and no Supabase-equivalent backend.
The closest mappings to the original checklist:

**The public API has no authentication.** `api/main.py:48-52` mounts
`CORSMiddleware` with `allow_origins=["*"]`, `allow_methods=["*"]`,
`allow_headers=["*"]`, and nothing in `api/main.py` checks an
`Authorization` header, a bearer token, or an API key on any route
(confirmed by grep: no `auth`, `Authorization`, `api_key`, or `Bearer`
string exists in `api/*.py`). Every endpoint, including `/api/revenue`
and `/api/jobs/summary`, is open to any origin with no credential check.
This is not called out anywhere in the README's threat-model section
(`README.md:499-524`), which discusses only copilot-level threats.

**The one deployed service that touches the warehouse uses admin
credentials, not a scoped role.** `warehouse/init/01_create_schemas.sql:9-16`
creates a read-only `reckon_reader` role, but only against the local
Postgres container; nothing in `infra/terraform/` or `infra/helm/` creates
an equivalent role or grant set on Redshift. The live API's DB credentials
come from `infra/helm/reckon/templates/secrets.yaml:9-13`, which is
populated at `helm-install` time from `warehouse.user`/`warehouse.password`
(`Makefile:154-159`), themselves the same `REDSHIFT_USER`/`REDSHIFT_PASSWORD`
Terraform used to create the Redshift admin account
(`infra/terraform/redshift.tf:4-6`, `infra/terraform/variables.tf:45`). So
the one public, unauthenticated HTTP service in this stack (finding above)
also queries the warehouse with full admin rights, since there is no
read-only role provisioned for it to use instead. Locally this is low
stakes (`reckon_dev` is a throwaway compose password); on a real deployment
it means an open API backed by an admin DB user.

**The copilot's read-only role, and the copilot itself, never reach the
live deployment.** `infra/helm/reckon/templates/` has Deployments for `api`
and `dashboard`, a CronJob for `pipeline`, and a StatefulSet-style resource
for `mongo`, but no copilot resource and no Dagster daemon resource, and
`Makefile` has no `copilot` or `dagster-daemon` install target. The copilot
only runs locally, either via `python -m copilot.cli` or wired into Claude
Desktop (`README.md:465-480`). That means the `reckon_reader` role the
README calls "the primary security control" (`README.md:505`) is proven by
tests only against local Postgres, and the service that would use it is
never deployed to the cloud target at all. Not a live bug (the control
surface it protects is not live either), but the README's threat model
reads as if it describes the production posture, when it only describes
the local one.

**"Which project the live site points at" has no fixed answer, by
design.** There is no standing live Reckon URL. `infra/terraform/variables.tf:1-5`
prefixes every AWS resource with `reckon`; region defaults to `us-east-1`
(`infra/terraform/variables.tf:7-11`); the account is whatever AWS credentials
the operator supplies, configured through `terraform.tfvars` (gitignored:
`.gitignore:24`, only `terraform.tfvars.example` is committed). The README
documents this as deliberate: `make up` stands the whole stack up, `make
down` tears it down, and a full hour costs about $3-5 (`README.md:226-227`).
So there is nothing to leak here beyond what `terraform.tfvars.example`
already shows (region and environment name), and a reviewer pointing their
own AWS account at `make up` gets a fresh, disposable deployment rather
than one shared "the" production instance.

**Dagster orchestration runs locally under a persistent daemon; on the
cluster it runs as a one-shot CLI call.** `docker-compose.yml` runs
`dagster-webserver` and `dagster-daemon` as long-lived services (services
at lines 112 and 132), which is what lets Dagster's own daily
`ScheduleDefinition` and the run-outcome sensors actually tick. The
Kubernetes CronJob (`infra/helm/reckon/templates/pipeline-cronjob.yaml`)
instead runs `scripts/run_pipeline.sh`, which calls `dagster job execute`
once per invocation (`scripts/run_pipeline.sh:38-41`) and pushes its own
success/failure metric directly (`scripts/run_pipeline.sh:47-53`), not
through a sensor. That path is self-contained and does not depend on a
daemon, so it is not broken, but it does mean the Dagster schedule object
and the sensors described in `CLAUDE.md:44-45` only ever run where a
daemon is alive, which today is local Docker Compose, not the cluster. The
cluster's actual schedule is the Kubernetes `CronJob.spec.schedule` field,
not Dagster's.

## Stripe and email: what actually exists

**There is no Stripe integration, live or test.** `ingest/extractors/stripe_payments.py:1-4`
states this directly: "In production this would use the Stripe API with
cursor-based pagination; here it generates realistic sample data." The
extractor (`generate_payment_records`, `ingest/extractors/stripe_payments.py:37-63`)
is a seeded random generator (`SEED = 77`, line 33); there is no Stripe SDK
dependency anywhere in `ingest/requirements.txt`, no webhook handler, and
no `STRIPE_` environment variable anywhere in the repo. A reviewer looking
for a Stripe webhook to test will not find one to test.

**There is no confirm-email toggle or Resend integration, because there is
no user signup.** The nearest thing to an email integration is Alertmanager
sending to Gmail SMTP for the `PipelineFreshnessBreach` alert
(`infra/helm/monitoring/values.yaml:90-102`). That config is handled the way
this repo consistently handles secrets: the committed file has only inert
placeholders (`smtp_auth_password: "REPLACE_AT_INSTALL"`, line 101), and the
`monitoring` Makefile target injects real values with `--set-string` from
`SMTP_USER`/`SMTP_PASSWORD`/`ALERT_EMAIL` env vars at install time
(`Makefile:180-187`), warning loudly if they are unset
(`Makefile:175-179`). Nothing about this needed correcting.

**One real gap next to it: the Grafana admin password has no equivalent
warning.** `infra/helm/monitoring/values.yaml:62-68` puts Grafana behind a
public `LoadBalancer` on plain HTTP (`service.type: LoadBalancer`, `port:
80`, no TLS) with a placeholder `adminPassword: reckon-admin`. The
`monitoring` target's unset-variable check (`Makefile:175-179`) covers
`SMTP_USER`, `SMTP_PASSWORD`, and `ALERT_EMAIL`, but not
`GRAFANA_ADMIN_PASSWORD`; if it is left unset, `make monitoring` installs
successfully with the internet-facing Grafana still on `admin` /
`reckon-admin` and prints nothing to say so.

**Metabase: two small, independently verifiable inconsistencies.**
`docker-compose.yml:183` hardcodes the host port mapping `"3001:3000"` and
never reads `${METABASE_PORT}`, even though `.env.example:31` documents
`METABASE_PORT=3000` as if setting it changes anything; it does not.
Separately, `metabase/setup.sh:10` defaults `MB_HOST` to
`http://localhost:3000`, which is the container-internal port, not the
host-mapped one. The script's own header comment documents the correct
`docker compose exec` form (`metabase/setup.sh:6`) right next to the
"or from the host" form (`metabase/setup.sh:7-8`) that will fail against a
closed port 3000 unless the reviewer separately exports
`MB_HOST=http://localhost:3001`. `docs/HANDBOOK.md:35` tells the reader to
just run `bash metabase/setup.sh` without that host-vs-container distinction.

## Tests, CI, and evals

Five independent suites, run by five independent CI jobs
(`.github/workflows/ci.yml`), deliberately kept apart because the pipeline,
API, and orchestration images each build from a different subset of the
repo and the dependency sets collide if combined (explained inline at
`.github/workflows/ci.yml:96-102` for the `orchestration` job specifically:
`dagster-dbt` pins protobuf-sensitive dependencies that conflict with
`dbt`'s own pins unless resolved in a single `pip install` call).

- **`ingest/tests`** (49 test functions, 4 files): pure unit tests, no
  external services. Cover generator determinism (fixed seeds: Aria 42,
  Stripe 77, Jobs 99, per `docs/DECISIONS.md:28`), record-field shape,
  date-window filtering, and the Redshift-safe SQL the loader emits (quoted
  `"raw"` schema, no `now()` default). Runs via `make test` /
  `pytest ingest/tests -v`, matching `CLAUDE.md:13`'s claim that this step
  is "database free."
- **`copilot/tests`** (60 test functions, 3 files): a mix of pure-logic
  tests (the SQL validator's forbidden-keyword regex, row cap, freshness
  threshold math) and DB-backed tests (role enforcement, stale/warn
  refusal, tool output matching a direct SQL query against the same
  fixture data). The DB-backed tests are gated by a `requires_db` marker
  that pings Postgres and skips, rather than fails, if it is unreachable
  (`copilot/tests/conftest.py:8-27`). CI runs only four explicitly named,
  DB-free test classes (`.github/workflows/ci.yml:29`); the DB-backed
  majority only runs against `make local`. The count (60) matches
  `README.md:776`'s claim exactly.
- **`api/tests`** (7 test functions, 1 file): pure unit tests of
  `classify_age()` plus one cross-check that the API's own copy of the
  24h/48h freshness thresholds matches `copilot/trust_gate.py`'s copy
  exactly (`api/tests/test_freshness.py:11-15`), since the API image
  builds from `api/` alone and cannot import the copilot package. No DB
  needed; its CI job installs `api/requirements.txt` alone specifically to
  mirror the real image build.
- **`orchestration/tests`** (53 test functions, 6 files): structural tests
  against the loaded Dagster definitions using an in-memory
  `DagsterInstance`, not a live warehouse (e.g. "every dbt model is an
  asset," "marts are downstream of ingest," "sensors are registered," in
  `orchestration/tests/test_definitions.py`), plus sensor-wiring tests with
  a monkeypatched Pushgateway call. `dagster definitions validate` runs as
  a hard gate before the tests in CI (`.github/workflows/ci.yml:117-120`).
- **`dashboard`** (17 assertions, 2 files, vitest): pure component-logic
  tests, e.g. `FreshnessBanner`'s age-formatting and status thresholds, no
  backend involved.
- **dbt** has no pytest suite. Its CI job (`lint-dbt`) runs `dbt deps` and
  `dbt parse` only, a syntax and dependency-graph check with no warehouse
  connection. The actual dbt tests (uniqueness, not-null, accepted values,
  freshness) live in `transform/models/*/schema.yml` and only run against a
  real warehouse via `dbt test`, which `README.md:215` correctly labels
  "(requires warehouse running)" and which is not part of CI. This is
  accurately documented, not a gap, but worth being explicit about: dbt's
  trust-gate tests are exercised locally or by the live pipeline, never by
  GitHub Actions.

**No evals framework.** There is no LLM-response scoring harness anywhere
in the repo (grepped for `eval`; nothing beyond ordinary code turned up).
The copilot's correctness claim rests entirely on the procedural tests
above, i.e. asserting a tool's returned numbers equal a direct SQL query
against the same fixture data (`copilot/tests/test_tools.py`), not on
scoring free-text answers. The README does not claim otherwise, so this is
a clarification for reviewers expecting an evals suite, not a contradiction.

## Checked and found no problem with

Five specific things worth naming because they looked, at first read, like
plausible doc drift, and were not:

- **The "60 tests" copilot claim** (`README.md:776`): counted
  `def test_` across `copilot/tests/*.py` directly; exactly 60.
- **"dbt multi-target profiles (dev=Postgres, prod=Redshift)"**
  (`README.md:755`): `transform/profiles.yml:1-16` defines exactly those
  two targets, reading the matching env vars for each.
- **"Security groups scoped: EKS nodes <-> Redshift only"**
  (`README.md:756`): `infra/terraform/security_groups.tf`'s Redshift
  security group has exactly one ingress rule, from the node security
  group, on port 5439.
- **The Kubernetes CronJob path re-running the pre-Dagster pipeline**: it
  does not. `infra/docker/pipeline.Dockerfile` and `docker-compose.yml`'s
  one-shot `pipeline` service share the same image and the same
  `scripts/run_pipeline.sh`, which invokes the current Dagster job
  (`reckon_full_refresh`) either way. The only real gap found nearby is the
  daemon/schedule point noted above, not this.
- **SMTP credential handling in `infra/helm/monitoring/values.yaml`**: this
  is the one place a real secret-shaped value lives near the repo, and it
  is correctly placeholder-only, injected at install time, never committed.
