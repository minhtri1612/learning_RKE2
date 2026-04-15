#!/usr/bin/env bash
# Ghi endpoint LB của clustermesh-apiserver management vào
# cilium/clustermesh-management-peer.yaml để spoke (dev/staging/prod) Helm
# trỏ tới cổng 2379 ổn định, không phụ thuộc IP Docker node.
#
# Sau khi chạy: git add/commit/push (Argo remote) hoặc sync từ repo local.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/cilium/clustermesh-management-peer.yaml"
HUB_CTX="${HUB_CTX:-kind-management}"
HUB_NS="${HUB_NS:-kube-system}"
SERVICE_NAME="${SERVICE_NAME:-clustermesh-apiserver}"
IP="$(kubectl --context "${HUB_CTX}" -n "${HUB_NS}" get svc "${SERVICE_NAME}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
if [[ -z "${IP}" ]]; then
  echo "Lỗi: chưa đọc được EXTERNAL-IP của ${SERVICE_NAME} trên ${HUB_CTX}/${HUB_NS}." >&2
  echo "Hãy đảm bảo MetalLB management đã chạy và service đã được cấp IP LoadBalancer." >&2
  exit 1
fi
cat >"${TARGET}" <<EOF
# AUTO — scripts/kind-clustermesh-peer-ip.sh — endpoint clustermesh-apiserver của management
clustermesh:
  config:
    clusters:
      - name: management
        port: 2379
        ips:
          - ${IP}
EOF
echo "OK: đã ghi ${IP} -> ${TARGET}"
