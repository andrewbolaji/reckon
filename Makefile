SHELL := /bin/bash
.DEFAULT_GOAL := help

TF_DIR       := infra/terraform
HELM_DIR     := infra/helm/reckon
RELEASE      := reckon
NAMESPACE    := reckon
TAG          ?= latest

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
	python -m pytest ingest/tests/ -v

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
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install $(RELEASE) $(HELM_DIR) \
		--namespace $(NAMESPACE) \
		--set images.pipeline="$(ECR_PIPELINE):$(TAG)" \
		--set images.api="$(ECR_API):$(TAG)" \
		--set images.dashboard="$(ECR_DASHBOARD):$(TAG)" \
		--set images.pullPolicy=Always \
		--set warehouse.host="$(RS_HOST)" \
		--set warehouse.port="$(RS_PORT)" \
		--set warehouse.db="$(RS_DB)" \
		--set warehouse.user="$(REDSHIFT_USER)" \
		--set warehouse.password="$(REDSHIFT_PASSWORD)" \
		--set lake.bucket="$(S3_BUCKET)" \
		--set lake.region="$(REGION)" \
		--wait --timeout 5m

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall Helm release
	helm uninstall $(RELEASE) --namespace $(NAMESPACE) || true
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

# ---------- Cluster Monitoring ----------

.PHONY: monitoring
monitoring: ## Install kube-prometheus-stack + provision dashboards (committed values, zero clicks)
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
		--set-string grafana.adminPassword="$${GRAFANA_ADMIN_PASSWORD:-reckon-admin}" \
		--set-string alertmanager.config.global.smtp_from="$${SMTP_FROM:-$${SMTP_USER:-alerts@reckon.invalid}}" \
		--set-string alertmanager.config.global.smtp_auth_username="$${SMTP_USER:-alerts@reckon.invalid}" \
		--set-string alertmanager.config.global.smtp_auth_password="$${SMTP_PASSWORD:-REPLACE_AT_INSTALL}" \
		--set-string 'alertmanager.config.receivers[1].email_configs[0].to'="$${ALERT_EMAIL:-you@example.com}" \
		--wait --timeout 10m
	$(MAKE) dashboards
	@echo ""
	@echo "=== Monitoring installed ==="
	@echo "Grafana: http://$$(kubectl get svc -n $(MON_NAMESPACE) $(MON_RELEASE)-grafana -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo "Login:   admin / $${GRAFANA_ADMIN_PASSWORD:-reckon-admin}"
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
up: init infra images kubeconfig monitoring helm-install ## Full deploy: infra + images + monitoring + Helm
	@echo ""
	@echo "=== Reckon is live on AWS (with cluster monitoring) ==="
	@echo "Dashboard: $$(kubectl get svc -n $(NAMESPACE) $(RELEASE)-reckon-dashboard -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo "API:       $$(kubectl get svc -n $(NAMESPACE) $(RELEASE)-reckon-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo "Grafana:   http://$$(kubectl get svc -n $(MON_NAMESPACE) $(MON_RELEASE)-grafana -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo ""
	@echo "Run 'make pipeline-run' to trigger the first pipeline execution."
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
