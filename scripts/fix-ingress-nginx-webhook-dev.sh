#!/usr/bin/env bash
# Sửa lỗi "failed calling webhook validate.nginx.ingress.kubernetes.io" trên cluster dev.
# Chạy với VPN bật. Cách 1: đợi ingress-nginx sẵn sàng. Cách 2: tạm xóa webhook (workaround).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

export KUBECONFIG="$ROOT_DIR/kube_config_rke2_dev.yaml"

echo "=== 1. Kiểm tra ingress-nginx trên dev ==="
kubectl get pods -n ingress-nginx 2>/dev/null || true
kubectl get svc -n ingress-nginx 2>/dev/null || true

echo ""
echo "=== 2. Xóa webhook (cert unknown authority → Ingress apply fail) ==="
# Ưu tiên xóa dev-ingress-nginx-admission (từ ArgoCD chart). Tránh xóa rke2-ingress-nginx-admission nếu có.
for whook in dev-ingress-nginx-admission ingress-nginx-admission; do
  if kubectl get validatingwebhookconfiguration "$whook" 2>/dev/null; then
    kubectl delete validatingwebhookconfiguration "$whook" --ignore-not-found
    echo "  ✓ Đã xóa $whook. Vào ArgoCD bấm Sync lại meo-station-backend-dev."
    exit 0
  fi
done
echo "  Không tìm thấy dev-ingress-nginx-admission. Thử: kubectl get validatingwebhookconfiguration | grep ingress"
