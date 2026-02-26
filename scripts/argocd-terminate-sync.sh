#!/usr/bin/env bash
# Hủy sync đang kẹt (another operation is already in progress).
# Chạy với VPN bật, từ thư mục repo.
# Usage: ./scripts/argocd-terminate-sync.sh [app-name]
# Example: ./scripts/argocd-terminate-sync.sh dev-ingress-nginx

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="${1:-dev-ingress-nginx}"
export KUBECONFIG="$ROOT_DIR/kube_config_rke2_management.yaml"

echo "Hủy operation đang chạy cho app: $APP_NAME"
# spec.operation thường null rồi; operation thật nằm ở status.operationState
if kubectl patch application "$APP_NAME" -n argocd --type merge --subresource=status -p '{"operationState":null}' 2>/dev/null; then
  echo "  ✓ Đã xóa status.operationState."
elif kubectl patch application "$APP_NAME" -n argocd --type merge -p '{"status":{"operationState":null}}' 2>/dev/null; then
  echo "  ✓ Đã xóa status.operationState (merge)."
else
  echo "  Thử xóa bằng JSON patch:"
  kubectl patch application "$APP_NAME" -n argocd --type json -p '[{"op":"remove","path":"/status/operationState"}]' 2>/dev/null && echo "  ✓ Done." || true
fi

echo "  Đợi vài giây..."
sleep 3
echo "  Xong. Vào ArgoCD bấm Sync lại (hoặc đợi auto sync)."
