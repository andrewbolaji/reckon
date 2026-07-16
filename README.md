# Reckon

**A business-intelligence platform with an AI copilot** — by [AIntellect](https://github.com/AIntellect).

Reckon ingests a business's scattered operational data, pipelines it into a warehouse, surfaces dashboards, and lets a non-technical owner ask questions in plain English. One of its data sources is **Aria**, our live AI voice agent, so call data (volume, urgency, bookings, escalations) flows in alongside payments and jobs.

---

## Architecture

```mermaid
graph TB
    subgraph Sources
        A[Aria Voice Agent<br/>Call Records]
        B[Stripe<br/>Payments]
    end

    subgraph "Ingestion Layer"
        C[Python Extractors]
        D[Data Lake<br/>Local FS / S3]
        E[Raw Loader]
    end

    subgraph "Transform Layer"
        F[dbt Staging Models]
        G[dbt Mart Models]
        H[Data Trust Gate<br/>dbt tests + freshness]
    end

    subgraph Warehouse
        I[(PostgreSQL / Redshift)]
    end

    subgraph "Serving Layer"
        J[FastAPI]
        K[React Dashboard]
        L[Metabase — Phase 3]
    end

    subgraph "AI Copilot — Phase 4"
        M[MCP Server]
        N[Claude / Agent]
    end

    A --> C
    B --> C
    C --> D
    D --> E
    E --> I
    I --> F
    F --> G
    G --> H
    H --> I
    I --> J
    J --> K
    I --> M
    M --> N

    style H fill:#fbbf24,stroke:#92400e,color:#000
    style M fill:#818cf8,stroke:#4338ca,color:#fff
    style N fill:#818cf8,stroke:#4338ca,color:#fff
```

### AWS Cloud Architecture (Phase 2)

```mermaid
graph TB
    subgraph "AWS Cloud"
        subgraph "EKS Cluster (2 nodes)"
            API[API Deployment<br/>2 replicas]
            DASH[Dashboard Deployment<br/>2 replicas]
            PIPE[Pipeline CronJob<br/>every 6h]
        end

        subgraph "Data Stores"
            S3[S3 Data Lake<br/>versioned + encrypted]
            RS[Redshift Serverless<br/>8 RPU base]
        end

        subgraph "Container Registry"
            ECR[ECR<br/>3 repositories]
        end

        LB1[Load Balancer] --> API
        LB2[Load Balancer] --> DASH
        API --> RS
        PIPE --> S3
        PIPE --> RS
        ECR -.-> API
        ECR -.-> DASH
        ECR -.-> PIPE
    end

    subgraph "IaC"
        TF[Terraform]
        HELM[Helm Chart]
    end

    TF --> S3
    TF --> RS
    TF --> EKS Cluster
    TF --> ECR
    HELM --> API
    HELM --> DASH
    HELM --> PIPE

    style TF fill:#7c3aed,stroke:#5b21b6,color:#fff
    style HELM fill:#0ea5e9,stroke:#0284c7,color:#fff
```

## Project Structure

```
Reckon/
├── ingest/                  # Python extractors and data-lake writers
│   ├── extractors/          # Per-source extractors (Aria, Stripe)
│   ├── tests/               # Extractor unit tests
│   ├── config.py            # Config loader (env-var driven)
│   ├── lake.py              # Data-lake abstraction (local / S3)
│   ├── loader.py            # Raw-to-warehouse loader
│   └── pipeline.py          # Pipeline entrypoint
├── transform/               # dbt project
│   ├── models/staging/      # Cleaned, typed views
│   ├── models/marts/        # Business-logic tables
│   ├── dbt_project.yml
│   └── profiles.yml         # Config-driven (Postgres / Redshift)
├── warehouse/init/          # DDL scripts for schema init
├── api/                     # FastAPI serving layer
├── dashboard/               # React + Recharts dashboard
│   └── src/components/      # KPI cards, funnel chart, revenue chart
├── mcp/                     # MCP copilot server (Phase 4)
├── infra/
│   ├── terraform/           # AWS infrastructure (VPC, EKS, Redshift, S3, ECR, IAM)
│   ├── helm/reckon/         # Helm chart (API, dashboard, pipeline CronJob)
│   └── docker/              # Dockerfiles
├── scripts/                 # Pipeline and ECR push scripts
├── observability/           # Prometheus, Grafana, Loki (Phase 3)
├── .github/workflows/       # CI/CD (GitHub Actions)
├── docker-compose.yml       # One-command local dev
├── Makefile                 # make up / make down / make deploy
└── .env.example             # Environment template
```

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Run It

```bash
# 1. Clone and configure
git clone <repo-url> && cd Reckon
cp .env.example .env

# 2. Start everything
docker-compose up --build

# 3. What happens:
#    - PostgreSQL warehouse starts
#    - Pipeline runs: extracts sample data, loads to warehouse, runs dbt
#    - API starts on http://localhost:8000
#    - Dashboard starts on http://localhost:5173
```

### Verify

| Service     | URL                          | What to check                     |
|-------------|------------------------------|-----------------------------------|
| API health  | http://localhost:8000/health  | `{"status": "ok"}`               |
| Call funnel | http://localhost:8000/api/call-funnel | Daily funnel data         |
| Revenue     | http://localhost:8000/api/revenue     | Daily revenue data        |
| Dashboard   | http://localhost:5173         | Interactive charts and KPIs      |

### Run Tests Locally

```bash
# Extractor unit tests
pip install psycopg2-binary boto3 pytest
pytest ingest/tests/ -v

# dbt tests (requires warehouse running)
cd transform
pip install dbt-core dbt-postgres
dbt deps --profiles-dir .
dbt test --profiles-dir .
```

## Deploy to AWS

> **COST WARNING**: EKS (~$0.10/hr for the control plane + ~$0.08/hr for 2x t3.medium nodes),
> Redshift Serverless (~$0.36/RPU-hr, 8 RPU minimum when active), NAT Gateway (~$0.045/hr),
> and Load Balancers (~$0.025/hr each) all cost money while running. **Stand it up, verify,
> screenshot, tear it down.** A full stack running for 1 hour costs roughly $3-5. `make down`
> destroys everything completely.

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- Docker
- kubectl
- Helm 3

### Deploy

```bash
# 1. Configure Terraform variables
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
# Edit terraform.tfvars: set redshift_admin_password

# 2. Set Redshift credentials for Helm
export REDSHIFT_USER=reckon_admin
export REDSHIFT_PASSWORD=your_password_here

# 3. Deploy everything (Terraform + ECR push + Helm install)
make up

# 4. Trigger the first pipeline run
make pipeline-run

# 5. Check status
make status
```

The `make up` command:
1. Runs `terraform init` and `terraform apply` (VPC, EKS, Redshift, S3, ECR, IAM)
2. Builds all 3 Docker images and pushes to ECR
3. Updates kubeconfig for the new EKS cluster
4. Helm-installs the chart with all Terraform outputs wired in
5. Prints the LoadBalancer URLs for API and dashboard

### Access

| Service   | URL |
|-----------|-----|
| Dashboard | `kubectl get svc -n reckon reckon-reckon-dashboard -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'` |
| API       | `kubectl get svc -n reckon reckon-reckon-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'` |

### Redeploy (code changes only)

```bash
make deploy   # Rebuilds images, pushes to ECR, rolls out new pods
```

### Teardown

```bash
make down     # Helm uninstall + terraform destroy. Zero resources remain.
```

This deletes the EKS cluster, Redshift namespace, S3 bucket (force-emptied), ECR repos (force-deleted),
VPC, NAT gateway, load balancers, and all IAM roles. Nothing is left running or billing.

### Local Dev (unchanged from Phase 1)

```bash
docker compose up --build   # or: make local
```

---

## Data Pipeline

1. **Extract** — Python extractors generate realistic sample data for Aria call records and Stripe payments
2. **Land** — Raw JSON written to data lake (local filesystem, swappable to S3)
3. **Load** — Raw data loaded into `raw` schema in the warehouse
4. **Transform** — dbt staging models clean and type the data; mart models aggregate into business metrics
5. **Trust Gate** — dbt tests validate uniqueness, not-null, accepted values; source freshness checks ensure data is current
6. **Serve** — FastAPI reads from marts; React dashboard visualizes the funnel and revenue

## Data Trust Gate

Every model has dbt tests that enforce:
- **Uniqueness**: no duplicate `call_id` or `payment_id`
- **Not-null**: critical fields are always present
- **Accepted values**: `urgency`, `outcome`, and `status` are constrained to known values
- **Source freshness**: data older than 24h triggers a warning; older than 48h fails the pipeline

The pipeline uses `dbt build`, which runs tests inline — a failing test stops downstream models from materializing.

## Roadmap

### Phase 1 — Foundation
- [x] Monorepo scaffold
- [x] Two Python extractors with sample data
- [x] Data-lake abstraction (local / S3)
- [x] dbt staging + marts with tests and freshness
- [x] FastAPI serving layer
- [x] React dashboard (call funnel + revenue)
- [x] GitHub Actions CI
- [x] Docker Compose for local dev

### Phase 2 — Cloud and Kubernetes (current)
- [x] Terraform IaC: VPC, EKS cluster, Redshift Serverless, S3 data lake, ECR, IAM
- [x] Helm chart: API and dashboard Deployments, pipeline CronJob, K8s Secrets
- [x] ECR build-and-push scripts for all 3 images
- [x] Config-driven cloud swap (env vars + K8s Secrets, zero app code changes)
- [x] Makefile lifecycle: `make up` (full deploy), `make down` (full teardown), `make deploy` (redeploy)
- [x] dbt multi-target profiles (dev=Postgres, prod=Redshift)
- [x] Security groups scoped: EKS nodes <-> Redshift only

### Phase 3 — Observability
- [ ] OpenTelemetry instrumentation across Python services
- [ ] Prometheus metrics collection
- [ ] Grafana dashboards for pipeline health
- [ ] Loki for centralized logging
- [ ] Alerting (PagerDuty / Slack integration)
- [ ] Metabase for self-serve BI

### Phase 4 — AI Copilot
- [ ] MCP server exposing warehouse schema and safe query tool
- [ ] Read-only SQL guardrails (query validation, row limits)
- [ ] Trust-gate enforcement: copilot refuses to answer from stale/failing data
- [ ] Natural-language Q&A over business data via Claude
- [ ] Conversation memory and follow-up queries

## Tech Stack

| Layer         | Technology                              |
|---------------|-----------------------------------------|
| Ingestion     | Python, custom extractors               |
| Data Lake     | Local FS / AWS S3                       |
| Warehouse     | PostgreSQL (dev) / Redshift (prod)      |
| Transform     | dbt (staging + marts + tests)           |
| API           | FastAPI, psycopg2                       |
| Dashboard     | React, Recharts, Vite                   |
| Infra (local) | Docker, Docker Compose                  |
| Infra (cloud) | Terraform, AWS EKS, Helm, Kubernetes    |
| Cloud storage | AWS S3 (data lake), Redshift Serverless |
| Registry      | AWS ECR                                 |
| Networking    | VPC, NAT Gateway, Security Groups, IAM  |
| CI/CD         | GitHub Actions, Makefile                |
| AI (Phase 4)  | MCP, Claude                             |

---

*Built by AIntellect*
