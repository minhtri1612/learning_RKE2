#!/usr/bin/env bash
# Xem logs của ingress-nginx trên cluster dev (controller pods).
# Chạy với VPN bật.
# Usage: ./scripts/logs-dev-ingress-nginx.sh [--follow] [--previous]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

export KUBECONFIG="$ROOT_DIR/kube_config_rke2_dev.yaml"
NS="ingress-nginx"
LABEL="app.kubernetes.io/name=ingress-nginx"

echo "=== Pods trong $NS (cluster dev) ==="
kubectl get pods -n "$NS" -l "$LABEL" 2>/dev/null || kubectl get pods -n "$NS" 2>/dev/null || { echo "Namespace $NS không tồn tại hoặc không có quyền."; exit 1; }

echo ""
echo "=== Logs controller (deployment *-controller) ==="
if kubectl get deployment -n "$NS" -o name 2>/dev/null | grep -q controller; then
  kubectl logs -n "$NS" deployment/dev-ingress-nginx-controller --tail=100 "$@" 2>/dev/null || \
  kubectl logs -n "$NS" -l app.kubernetes.io/component=controller --tail=100 "$@" 2>/dev/null || true
else
  CONTROLLER_POD=$(kubectl get pods -n "$NS" -o name 2>/dev/null | grep "\-controller-" | grep -v admission | head -1)
  if [[ -n "$CONTROLLER_POD" ]]; then
    kubectl logs -n "$NS" "$CONTROLLER_POD" --tail=100 "$@" 2>/dev/null
  else
    echo "Không tìm thấy pod controller."
    exit 1
  fi
fi
