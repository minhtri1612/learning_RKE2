#!/usr/bin/env bash
# Apply Argo CD Applications cho một env (dev|prod).
# Chạy từ thư mục gốc repo (có argocd/environments/).
# Ví dụ: ./scripts/apply-argocd-apps.sh dev
set -e
ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ARGOCD_ENV_DIR="${REPO_DIR}/argocd/environments/${ENV}"

if [[ ! -d "$ARGOCD_ENV_DIR" ]]; then
  echo "Error: argocd/environments/${ENV}/ not found."
  echo "Usage: $0 [dev|prod]"
  exit 1
fi

echo "Applying Argo CD apps for env=${ENV} from ${ARGOCD_ENV_DIR}..."
kubectl apply -f "${ARGOCD_ENV_DIR}/be-application.yaml"
kubectl apply -f "${ARGOCD_ENV_DIR}/data-application.yaml"
echo "Done. Refresh/Sync apps in Argo CD UI."
