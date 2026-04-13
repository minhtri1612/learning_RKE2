#!/usr/bin/env bash
# Ghi IP Docker (mạng kind) của management-control-plane vào
# cilium/clustermesh-management-peer.yaml để spoke (dev/staging/prod) Helm
# trỏ tới clustermesh-apiserver NodePort 32379 trên hub.
#
# Sau khi chạy: git add/commit/push (Argo remote) hoặc sync từ repo local.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/cilium/clustermesh-management-peer.yaml"
IP="$(docker inspect management-control-plane --format '{{(index .NetworkSettings.Networks "kind").IPAddress}}' 2>/dev/null || true)"
if [[ -z "${IP}" ]]; then
  echo "Lỗi: không đọc được IP của management-control-plane (container có tên đúng không?)." >&2
  exit 1
fi
cat >"${TARGET}" <<EOF
# AUTO — scripts/kind-clustermesh-peer-ip.sh — IP mạng Docker kind của management-control-plane
clustermesh:
  config:
    clusters:
      management:
        port: 32379
        ips:
          - ${IP}
EOF
echo "OK: đã ghi ${IP} -> ${TARGET}"
