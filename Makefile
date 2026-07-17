SHELL := /bin/bash
.DEFAULT_GOAL := help

TF_DIR       := infra/terraform
HELM_DIR     := infra/helm/reckon
RELEASE      := reckon
NAMESPACE    := reckon
TAG          ?= latest

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

# ---------- Pipeline (manual trigger) ----------

.PHONY: pipeline-run
pipeline-run: ## Trigger a one-off pipeline job on EKS
	kubectl create job --namespace $(NAMESPACE) \
		--from=cronjob/$(RELEASE)-reckon-pipeline \
		$(RELEASE)-pipeline-manual-$$(date +%s)

# ---------- Full Lifecycle ----------

.PHONY: up
up: init infra images kubeconfig helm-install ## Full deploy: infra + images + Helm
	@echo ""
	@echo "=== Reckon is live on AWS ==="
	@echo "Dashboard: $$(kubectl get svc -n $(NAMESPACE) $(RELEASE)-reckon-dashboard -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo "API:       $$(kubectl get svc -n $(NAMESPACE) $(RELEASE)-reckon-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
	@echo ""
	@echo "Run 'make pipeline-run' to trigger the first pipeline execution."
	@echo "Run 'make down' when done to avoid ongoing costs."

.PHONY: down
down: helm-uninstall infra-destroy ## Full teardown: Helm uninstall + Terraform destroy
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
