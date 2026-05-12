#!/bin/bash
# Sau khi dev master reboot, script này:
# 1) Poll cho đến khi API 10.1.101.94:6443 accessible
# 2) Ngay lập tức xóa Cilium DaemonSet (trước khi BPF programs block API)
# 3) Thông báo để mày chạy configure.py dev

set -e
export KUBECONFIG="/home/minhtri/Downloads/practice_RKE2/kube_config_rke2_dev.yaml"
API="https://10.1.101.94:6443"

echo "=== Polling API $API (Ctrl+C để dừng) ==="
while true; do
  if curl -sk --noproxy '*' --connect-timeout 4 "$API/readyz" > /dev/null 2>&1; then
    echo "[$(date +%T)] ✓ API UP — xóa Cilium DS ngay..."
    break
  fi
  echo -n "."
  sleep 3
done

# API vừa up — xóa Cilium resources ngay trước khi BPF programs attach
kubectl delete daemonset cilium -n kube-system --ignore-not-found 2>/dev/null && \
  echo "  ✓ Cilium DaemonSet deleted" || echo "  (DaemonSet already gone)"
kubectl delete deployment cilium-operator -n kube-system --ignore-not-found 2>/dev/null && \
  echo "  ✓ cilium-operator deleted" || true

echo ""
echo "=== XONG. Chạy ngay: ==="
echo "  ./configure.py dev"
