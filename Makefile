SHELL := /bin/bash
.DEFAULT_GOAL := help
.NOTPARALLEL: up down deploy

TF_DIR       := infra/terraform
HELM_DIR     := infra/helm/reckon
RELEASE      := reckon
NAMESPACE    := reckon
TAG          ?= $(shell git rev-parse --verify HEAD)
WAREHOUSE_SECRET ?= $(RELEASE)-reckon-warehouse

# ---------- Cluster Monitoring (kube-prometheus-stack) ----------
MON_RELEASE   := kps
MON_NAMESPACE := monitoring
MON_CHART     := prometheus-community/kube-prometheus-stack
MON_VALUES    := infra/helm/monitoring/values.yaml
MON_DASH_DIR  := infra/helm/monitoring/dashboards
MON_REPO_URL  := https://prometheus-community.github.io/helm-charts

# ---------- Local Dev ----------

.PHONY: local
local: ## Start local dev environment with docker-compose
	docker compose up --build

.PHONY: local-down
local-down: ## Stop local dev environment
	docker compose down -v

.PHONY: observability
observability: ## Start local stack with full observability (Prometheus, Grafana, Loki)
	OTEL_ENABLED=true docker compose --profile observability up --build

.PHONY: observability-down
observability-down: ## Stop observability stack and remove volumes
	docker compose --profile observability down -v

.PHONY: test
test: ## Run unit tests
	$(PY) -m pytest ingest/tests/ -v

# ---------- Orchestration (Dagster) ----------

# Every target runs through the venv so they work without an activated shell,
# and against the compose warehouse and Mongo on their published host ports.
PY            := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
DAGSTER       := $(shell [ -x .venv/bin/dagster ] && echo .venv/bin/dagster || echo dagster)
DAGSTER_DEFS  := orchestration.definitions
DAGSTER_ENV   := DAGSTER_HOME=$(CURDIR)/.dagster_home \
                 POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
                 POSTGRES_DB=reckon POSTGRES_USER=reckon POSTGRES_PASSWORD=reckon_dev \
                 MONGO_URI=mongodb://localhost:27017 \
                 DATA_LAKE_PATH=$(CURDIR)/data/lake
# The whole demo window, so one command fills the warehouse end to end.
WINDOW_START  ?= $(shell $(PY) -c "from orchestration.partitions import full_window; print(full_window()[0])")
WINDOW_END    ?= $(shell $(PY) -c "from orchestration.partitions import full_window; print(full_window()[1])")
FROM          ?= $(WINDOW_START)
TO            ?= $(WINDOW_END)

.PHONY: dagster-manifest
dagster-manifest: ## Build the dbt manifest the asset graph loads from
	@mkdir -p $(CURDIR)/.dagster_home
	cd transform && $(CURDIR)/.venv/bin/dbt deps --profiles-dir . \
		&& $(CURDIR)/.venv/bin/dbt parse --profiles-dir .

.PHONY: dagster-validate
dagster-validate: dagster-manifest ## Validate the Dagster definitions (the CI gate)
	$(DAGSTER_ENV) $(DAGSTER) definitions validate -m $(DAGSTER_DEFS)

.PHONY: dagster-dev
dagster-dev: dagster-manifest ## Open the Dagster UI at http://localhost:3000
	$(DAGSTER_ENV) $(DAGSTER) dev -m $(DAGSTER_DEFS)

## dagster-run, dagster-backfill, and dagster-break all execute inside the
## running dagster-webserver container rather than through the host venv.
## The daemon's schedule, sensors, and run history live in the DAGSTER_HOME
## Docker volume; a host-side `dagster job execute` writes to a completely
## separate local .dagster_home instead, invisible to that daemon. A run
## started that way would never appear in the UI and would never reach the
## failure/success sensors, no matter how correct the sensors themselves
## are. Needs `make local` (or `make observability`) already running.

.PHONY: dagster-run
dagster-run: ## Materialise the whole DAG for the demo window (needs `make local`)
	docker compose exec -T dagster-webserver \
		dagster job execute -m $(DAGSTER_DEFS) -j reckon_full_refresh \
		--tags '{"dagster/asset_partition_range_start": "$(WINDOW_START)", "dagster/asset_partition_range_end": "$(WINDOW_END)"}'

.PHONY: dagster-backfill
dagster-backfill: ## Refill an ingest window: make dagster-backfill FROM=2026-07-01 TO=2026-07-07 (needs `make local`)
	docker compose exec -T dagster-webserver \
		dagster asset materialize -m $(DAGSTER_DEFS) \
		--select 'aria_calls_raw,stripe_payments_raw,mongo_jobs_raw' \
		--partition-range '$(FROM)...$(TO)'

.PHONY: dagster-break
dagster-break: ## Demo: fail a source and watch downstream halt (SOURCE=stripe_payments_raw, needs `make local`)
	docker compose exec -T -e RECKON_BREAK_SOURCE=$(or $(SOURCE),stripe_payments_raw) dagster-webserver \
		dagster job execute -m $(DAGSTER_DEFS) -j reckon_full_refresh \
		--tags '{"dagster/asset_partition_range_start": "$(WINDOW_START)", "dagster/asset_partition_range_end": "$(WINDOW_END)"}'

.PHONY: dagster-test
dagster-test: ## Run the orchestration tests
	$(PY) -m pytest orchestration/tests -q

# ---------- Infrastructure ----------

.PHONY: init
init: ## Initialize Terraform
	terraform -chdir=$(TF_DIR) init

.PHONY: plan
plan: ## Show Terraform plan
	terraform -chdir=$(TF_DIR) plan

.PHONY: infra
infra: ## Apply Terraform (provision AWS resources)
	terraform -chdir=$(TF_DIR) apply

.PHONY: infra-destroy
infra-destroy: ## Destroy all AWS infrastructure
	terraform -chdir=$(TF_DIR) destroy

# ---------- Container Images ----------

.PHONY: images
images: ## Build and push all images to ECR
	@if [ "$(TAG)" = "$$(git rev-parse --verify HEAD)" ] && [ -n "$$(git status --porcelain)" ]; then \
		echo ">> Refusing to publish dirty work under a commit-SHA tag." >&2; \
		echo ">> Commit the changes or pass an explicit TAG for an intentional snapshot." >&2; \
		exit 1; \
	fi
	chmod +x scripts/ecr_push.sh
	./scripts/ecr_push.sh $(TAG)

# ---------- Kubernetes ----------

.PHONY: kubeconfig
kubeconfig: ## Update kubeconfig for the EKS cluster
	$(eval CLUSTER := $(shell terraform -chdir=$(TF_DIR) output -raw eks_cluster_name))
	$(eval REGION := $(shell terraform -chdir=$(TF_DIR) output -raw aws_region))
	aws eks update-kubeconfig --name $(CLUSTER) --region $(REGION)

.PHONY: helm-install
helm-install: ## Install/upgrade Helm release on EKS
	$(eval ECR_PIPELINE := $(shell terraform -chdir=$(TF_DIR) output -raw ecr_pipeline_url))
	$(eval ECR_API := $(shell terraform -chdir=$(TF_DIR) output -raw ecr_api_url))
	$(eval ECR_DASHBOARD := $(shell terraform -chdir=$(TF_DIR) output -raw ecr_dashboard_url))
	$(eval RS_HOST := $(shell terraform -chdir=$(TF_DIR) output -raw redshift_endpoint))
	$(eval RS_PORT := $(shell terraform -chdir=$(TF_DIR) output -raw redshift_port))
	$(eval RS_DB := $(shell terraform -chdir=$(TF_DIR) output -raw redshift_db_name))
	$(eval S3_BUCKET := $(shell terraform -chdir=$(TF_DIR) output -raw s3_data_lake_bucket))
	$(eval REGION := $(shell terraform -chdir=$(TF_DIR) output -raw aws_region))
	@if [ -z "$${REDSHIFT_PASSWORD:-}" ]; then \
		echo ">> REDSHIFT_PASSWORD must be set before helm-install" >&2; \
		exit 1; \
	fi
	@kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@set -euo pipefail; \
		{ \
			printf '%s\n' \
				"WAREHOUSE_TYPE=redshift" \
				"POSTGRES_HOST=$(RS_HOST)" \
				"POSTGRES_PORT=$(RS_PORT)" \
				"POSTGRES_DB=$(RS_DB)" \
				"POSTGRES_USER=$${REDSHIFT_USER:-reckon_admin}" \
				"POSTGRES_PASSWORD=$${REDSHIFT_PASSWORD}" \
				"REDSHIFT_HOST=$(RS_HOST)" \
				"REDSHIFT_PORT=$(RS_PORT)" \
				"REDSHIFT_DB=$(RS_DB)" \
				"REDSHIFT_USER=$${REDSHIFT_USER:-reckon_admin}" \
				"REDSHIFT_PASSWORD=$${REDSHIFT_PASSWORD}" \
				"DATA_LAKE_TYPE=s3" \
				"S3_BUCKET=$(S3_BUCKET)" \
				"AWS_REGION=$(REGION)"; \
		} | kubectl create secret generic $(WAREHOUSE_SECRET) \
			--namespace $(NAMESPACE) \
			--from-env-file=/dev/stdin \
			--dry-run=client -o yaml | kubectl apply -f -; \
		secret_revision=$$(kubectl get secret $(WAREHOUSE_SECRET) \
			--namespace $(NAMESPACE) -o jsonpath='{.metadata.resourceVersion}'); \
		helm upgrade --install $(RELEASE) $(HELM_DIR) \
		--namespace $(NAMESPACE) \
		--set-string images.pipeline="$(ECR_PIPELINE):$(TAG)" \
		--set-string images.api="$(ECR_API):$(TAG)" \
		--set-string images.dashboard="$(ECR_DASHBOARD):$(TAG)" \
		--set-string images.pullPolicy=IfNotPresent \
		--set-string warehouse.existingSecret="$(WAREHOUSE_SECRET)" \
		--set-string warehouse.secretRevision="$${secret_revision}" \
		--wait --timeout 20m

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall Helm release
	helm uninstall $(RELEASE) --namespace $(NAMESPACE) || true
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

# ---------- Cluster Monitoring ----------

.PHONY: monitoring
monitoring: ## Install kube-prometheus-stack + provision dashboards (committed values, zero clicks)
	@if [ -z "$${GRAFANA_ADMIN_PASSWORD:-}" ]; then \
		echo ">> GRAFANA_ADMIN_PASSWORD must be set before 'make monitoring'." >&2; \
		echo ">> Refusing to install Grafana under a password committed to this repo:" >&2; \
		echo ">>   export GRAFANA_ADMIN_PASSWORD=\"\$$(openssl rand -base64 24)\"" >&2; \
		exit 1; \
	fi
	helm repo add prometheus-community $(MON_REPO_URL) 2>/dev/null || true
	helm repo update prometheus-community
	kubectl create namespace $(MON_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@if [ -z "$$SMTP_USER" ] || [ -z "$$SMTP_PASSWORD" ] || [ -z "$$ALERT_EMAIL" ]; then \
		echo ">> WARNING: SMTP_USER / SMTP_PASSWORD / ALERT_EMAIL not all set."; \
		echo ">> Email alerts will NOT deliver until you set them and re-run 'make monitoring':"; \
		echo ">>   export SMTP_USER=you@gmail.com SMTP_PASSWORD=<gmail-app-password> ALERT_EMAIL=you@gmail.com"; \
	fi
	helm upgrade --install $(MON_RELEASE) $(MON_CHART) \
		--namespace $(MON_NAMESPACE) \
		-f $(MON_VALUES) \
		--set-string grafana.adminPassword="$${GRAFANA_ADMIN_PASSWORD}" \
		--set-string alertmanager.config.global.smtp_from="$${SMTP_FROM:-$${SMTP_USER:-alerts@reckon.invalid}}" \
		--set-string alertmanager.config.global.smtp_auth_username="$${SMTP_USER:-alerts@reckon.invalid}" \
		--set-string alertmanager.config.global.smtp_auth_password="$${SMTP_PASSWORD:-REPLACE_AT_INSTALL}" \
		--set-string 'alertmanager.config.receivers[1].email_configs[0].to'="$${ALERT_EMAIL:-you@example.com}" \
		--wait --timeout 10m
	$(MAKE) dashboards
	@echo ""
	@echo "=== Monitoring installed ==="
	@echo "Grafana is ClusterIP only. Forward the port to reach it:"
	@echo "  kubectl port-forward -n $(MON_NAMESPACE) svc/$(MON_RELEASE)-grafana 3000:80"
	@echo "  then open http://localhost:3000 and log in as admin with GRAFANA_ADMIN_PASSWORD."
	@echo "Dashboards (Reckon Health, Pipeline Health, API Health) provision automatically."

.PHONY: dashboards
dashboards: ## (Re)provision Grafana dashboards from committed JSON as labelled ConfigMaps
	kubectl create configmap reckon-dashboards \
		--namespace $(MON_NAMESPACE) \
		--from-file=$(MON_DASH_DIR) \
		--dry-run=client -o yaml | \
		kubectl label --local -f - grafana_dashboard=1 -o yaml | \
		kubectl apply -f -

.PHONY: monitoring-down
monitoring-down: ## Uninstall monitoring stack and release its LoadBalancer
	helm uninstall $(MON_RELEASE) --namespace $(MON_NAMESPACE) || true
	kubectl delete configmap reckon-dashboards -n $(MON_NAMESPACE) --ignore-not-found
	kubectl delete namespace $(MON_NAMESPACE) --ignore-not-found

# ---------- Pipeline (manual trigger) ----------

.PHONY: pipeline-run
pipeline-run: ## Trigger a one-off pipeline job on EKS
	kubectl create job --namespace $(NAMESPACE) \
		--from=cronjob/$(RELEASE)-reckon-pipeline \
		$(RELEASE)-pipeline-manual-$$(date +%s)

# ---------- Full Lifecycle ----------

.PHONY: up
up: init infra images kubeconfig monitoring helm-install ## Guided full deploy: infra + images + monitoring + Helm
	@echo ""
	@echo "=== Reckon is live on AWS (with cluster monitoring) ==="
	@echo "Nothing is published to the internet. Forward a port to reach each service:"
	@echo "  Dashboard: kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-reckon-dashboard 8080:80   then http://localhost:8080"
	@echo "  API:       kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-reckon-api 8000:80         then http://localhost:8000/health"
	@echo "  Grafana:   kubectl port-forward -n $(MON_NAMESPACE) svc/$(MON_RELEASE)-grafana 3000:80    then http://localhost:3000"
	@echo ""
	@echo "The post-install bootstrap job seeded the warehouse."
	@echo "Run 'make down' when done to avoid ongoing costs."

.PHONY: down
down: helm-uninstall monitoring-down infra-destroy ## Full teardown: Helm + monitoring uninstall + Terraform destroy
	@echo ""
	@echo "=== All AWS resources destroyed. Nothing left running. ==="

.PHONY: deploy
deploy: images helm-install ## Image-only redeploy (no infra changes)
	@echo "=== Redeployed with new images ==="

# ---------- Status ----------

.PHONY: status
status: ## Show cluster status
	@echo "--- Pods ---"
	kubectl get pods -n $(NAMESPACE)
	@echo ""
	@echo "--- Services ---"
	kubectl get svc -n $(NAMESPACE)
	@echo ""
	@echo "--- CronJobs ---"
	kubectl get cronjobs -n $(NAMESPACE)

# ---------- Help ----------

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
