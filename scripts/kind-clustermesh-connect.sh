#!/usr/bin/env bash
# Mô hình chuẩn: mọi cluster đều có clustermesh-apiserver (clustermesh.useAPIServer=true).
# Nếu spoke tắt apiserver, dùng script fallback: scripts/kind-clustermesh-sync-spoke-from-hub.sh
#
# Thứ tự gợi ý: hub trước, rồi từng spoke. Yêu cầu cilium CLI + kubectl contexts.
#
# Xem thêm: https://docs.cilium.io/en/stable/network/clustermesh/
set -euo pipefail
if ! command -v cilium >/dev/null 2>&1; then
  echo "Cần cilium CLI trong PATH." >&2
  exit 1
fi
echo "Bật / đồng bộ clustermesh (idempotent nếu đã bật)..."
cilium clustermesh enable --context kind-management 2>/dev/null || true
for ctx in kind-dev kind-staging kind-prod; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  cilium clustermesh enable --context "${ctx}" 2>/dev/null || true
done
echo "Connect hub -> spoke..."
for ctx in kind-dev kind-staging kind-prod; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  cilium clustermesh connect --context kind-management --destination-context "${ctx}" || true
done
echo "Xong. Chạy: scripts/kind-clustermesh-status.sh"
