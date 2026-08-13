#!/usr/bin/env bash
set -euo pipefail
#
# Build and push all images to ECR.
# Usage: ./scripts/ecr_push.sh [TAG]
# Reads ECR URLs from Terraform outputs.
#

if [[ $# -eq 0 && -n "$(git status --porcelain)" ]]; then
  echo ">> Refusing to publish dirty work under a commit-SHA tag." >&2
  echo ">> Commit the changes or pass an explicit tag." >&2
  exit 1
fi

TAG="${1:-$(git rev-parse --verify HEAD)}"
TF_DIR="infra/terraform"
PLATFORM="linux/amd64"

echo "=== ECR Build & Push (tag: ${TAG}) ==="

# Get outputs from Terraform
REGION=$(terraform -chdir="${TF_DIR}" output -raw aws_region)
ECR_PIPELINE=$(terraform -chdir="${TF_DIR}" output -raw ecr_pipeline_url)
ECR_API=$(terraform -chdir="${TF_DIR}" output -raw ecr_api_url)
ECR_DASHBOARD=$(terraform -chdir="${TF_DIR}" output -raw ecr_dashboard_url)
ACCOUNT_ID=$(echo "${ECR_PIPELINE}" | cut -d. -f1)

# Authenticate Docker with ECR
echo "[1/4] Authenticating with ECR..."
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Build and push pipeline image
echo "[2/4] Building and pushing pipeline image..."
docker build --platform "${PLATFORM}" -t "${ECR_PIPELINE}:${TAG}" -f infra/docker/pipeline.Dockerfile .
docker push "${ECR_PIPELINE}:${TAG}"

# Build and push API image
echo "[3/4] Building and pushing API image..."
docker build --platform "${PLATFORM}" -t "${ECR_API}:${TAG}" -f api/Dockerfile api/
docker push "${ECR_API}:${TAG}"

# Build and push dashboard image
echo "[4/4] Building and pushing dashboard image..."
docker build --platform "${PLATFORM}" -t "${ECR_DASHBOARD}:${TAG}" -f dashboard/Dockerfile dashboard/
docker push "${ECR_DASHBOARD}:${TAG}"

echo ""
echo "=== All images pushed ==="
echo "  Pipeline:  ${ECR_PIPELINE}:${TAG}"
echo "  API:       ${ECR_API}:${TAG}"
echo "  Dashboard: ${ECR_DASHBOARD}:${TAG}"
