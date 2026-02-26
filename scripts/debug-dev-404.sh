#!/usr/bin/env bash
# Chạy khi đã bật VPN. Kiểm tra tại sao meo-stationery-dev.local 404.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== 1. Repo ArgoCD đang dùng (phải trùng repo bạn push cluster-dev.yaml) ==="
grep -r "repoURL" argocd/bootstrap/02-root-app.yaml argocd/appsets/appset-applications.yaml 2>/dev/null | head -5
echo ""
echo "  Git remote của thư mục này:"
git remote -v 2>/dev/null || true
echo ""

echo "=== 2. Trên cluster DEV: pods / ingress / svc (KUBECONFIG=dev) ==="
export KUBECONFIG="$ROOT_DIR/kube_config_rke2_dev.yaml"
if [[ ! -f "$KUBECONFIG" ]]; then
  echo "  Không có kube_config_rke2_dev.yaml. Chạy provision.py dev trước."
else
  echo "  Namespace meo-stationery:"
  kubectl get pods,svc,ingress -n meo-stationery 2>/dev/null || echo "  (namespace không tồn tại hoặc không có resource)"
  echo ""
  echo "  Namespace database:"
  kubectl get pods -n database 2>/dev/null || echo "  (namespace không tồn tại)"
  echo ""
  echo "  Ingress toàn cluster:"
  kubectl get ingress -A 2>/dev/null || true
fi
echo ""

echo "=== 3. Trên MANAGEMENT: ArgoCD apps đích dev (KUBECONFIG=management) ==="
export KUBECONFIG="$ROOT_DIR/kube_config_rke2_management.yaml"
if [[ ! -f "$KUBECONFIG" ]]; then
  echo "  Không có kube_config_rke2_management.yaml."
else
  echo "  Cluster secret dev (server = IP ArgoCD dùng để gọi dev):"
  kubectl get secret cluster-dev -n argocd -o jsonpath='{.data.server}' 2>/dev/null | base64 -d 2>/dev/null || true
  echo ""
  echo "  Ứng dụng ArgoCD cho dev:"
  kubectl get applications -n argocd 2>/dev/null | grep -E "NAME|dev" || true
  echo ""
  echo "  Chi tiết backend dev (nếu có):"
  kubectl get application meo-station-backend-dev -n argocd -o jsonpath='{.status.sync.status}{" "}{.status.health.status}{" "}{.status.conditions[*].message}' 2>/dev/null || true
  echo ""
fi
echo ""
echo "--- Gợi ý ---"
echo "  - Nếu dev cluster trống (không pod meo-stationery): ArgoCD chưa deploy được xuống dev (kiểm tra cluster-dev secret IP có đúng master dev hiện tại không)."
echo "  - Nếu có pod nhưng 404: kiểm tra ingress host meo-stationery-dev.local và backend service."
echo "  - ArgoCD sync từ repo learning_RKE2. Nếu bạn push từ repo khác (practice_RKE2), phải push argocd/clusters/ lên learning_RKE2 hoặc đổi ArgoCD sang repo bạn dùng."
