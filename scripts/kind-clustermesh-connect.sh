#!/usr/bin/env bash
# GitOps thuần của repo này: spoke không deploy clustermesh-apiserver
# (clustermesh.useAPIServer=false), nên `cilium clustermesh connect` không phù hợp.
# Script này giữ tên cũ để tương thích, nhưng sẽ chạy flow sync declarative.
#
# Thứ tự gợi ý: hub trước, rồi từng spoke. Yêu cầu cilium CLI + kubectl contexts.
#
# Xem thêm: https://docs.cilium.io/en/stable/network/clustermesh/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNC_SCRIPT="${ROOT}/scripts/kind-clustermesh-sync-spoke-from-hub.sh"
if [[ ! -x "${SYNC_SCRIPT}" ]]; then
  chmod +x "${SYNC_SCRIPT}" 2>/dev/null || true
fi
if [[ ! -f "${SYNC_SCRIPT}" ]]; then
  echo "Thiếu ${SYNC_SCRIPT}" >&2
  exit 1
fi
echo "Repo đang dùng GitOps flow, chuyển qua ${SYNC_SCRIPT}..."
"${SYNC_SCRIPT}"
echo "Xong. Kiểm tra: cilium clustermesh status --context kind-management"
