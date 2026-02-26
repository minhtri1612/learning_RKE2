#!/usr/bin/env bash
# Xóa validating webhook ingress-nginx để Ingress apply được (tránh lỗi cert webhook).
# Usage: ./scripts/fix-ingress-nginx-webhook.sh [dev|prod]
# Gọi tự động từ configure.py dev/prod.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

env="${1:-}"
if [[ -z "$env" || "$env" != "dev" && "$env" != "prod" ]]; then
  echo "Usage: $0 dev|prod"
  exit 1
fi

export KUBECONFIG="$ROOT_DIR/kube_config_rke2_${env}.yaml"
if [[ ! -f "$KUBECONFIG" ]]; then
  echo "  ⚠ Kubeconfig not found: $KUBECONFIG — skip webhook delete."
  exit 0
fi

# ApplicationSet: name = {{name}}-ingress-nginx → webhook = dev-ingress-nginx-admission / prod-ingress-nginx-admission
webhook_name="${env}-ingress-nginx-admission"
if kubectl get validatingwebhookconfiguration "$webhook_name" &>/dev/null; then
  kubectl delete validatingwebhookconfiguration "$webhook_name" --ignore-not-found
  echo "  ✓ Deleted $webhook_name (Ingress apply sẽ không còn lỗi webhook)."
else
  echo "  ⏭ $webhook_name chưa có (ArgoCD chưa sync ingress-nginx?) — bỏ qua."
fi
