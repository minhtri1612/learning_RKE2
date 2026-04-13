#!/usr/bin/env bash
# Hub–spoke với clustermesh.useAPIServer=false: chart không tạo clustermesh-apiserver-remote-cert trên spoke;
# cilium clustermesh connect cũng không chạy (CLI đòi clustermesh-apiserver trên destination).
# Script này: (1) ghi IP hub vào cilium/clustermesh-management-peer.yaml (2) copy secret TLS etcd từ hub sang mọi spoke (3) restart cilium.
#
# Sau đó cần sync Helm/Argo để DaemonSet nhận hostAliases + encryption từ Git (xem cuối script).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HUB_CTX="${HUB_CTX:-kind-management}"
HUB_NS="${HUB_NS:-kube-system}"
SECRET_NAME="clustermesh-apiserver-remote-cert"
PEER_SCRIPT="${ROOT}/scripts/kind-clustermesh-peer-ip.sh"

if [[ ! -f "${PEER_SCRIPT}" ]]; then
  echo "Thiếu ${PEER_SCRIPT}" >&2
  exit 1
fi

echo "==> Cập nhật IP hub -> cilium/clustermesh-management-peer.yaml"
bash "${PEER_SCRIPT}"

if ! kubectl --context "${HUB_CTX}" get secret -n "${HUB_NS}" "${SECRET_NAME}" &>/dev/null; then
  echo "Lỗi: trên hub (${HUB_CTX}) chưa có secret ${SECRET_NAME}. Kiểm tra Cilium ClusterMesh trên management." >&2
  exit 1
fi

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
kubectl --context "${HUB_CTX}" -n "${HUB_NS}" get secret "${SECRET_NAME}" -o yaml \
  | sed '/^\s*resourceVersion:/d;/^\s*uid:/d;/^\s*creationTimestamp:/d;/^\s*selfLink:/d;/^\s*namespace:/d' \
  > "${TMP}"

for ctx in kind-dev kind-staging kind-prod; do
  if ! kubectl config get-contexts -o name | grep -qx "${ctx}"; then
    echo "Bỏ qua (không có context): ${ctx}"
    continue
  fi
  echo "==> ${ctx}: apply ${SECRET_NAME} + rollout restart ds/cilium"
  kubectl --context "${ctx}" -n "${HUB_NS}" apply -f "${TMP}"
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout restart ds/cilium
done

for ctx in kind-dev kind-staging kind-prod; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout status ds/cilium --timeout=180s
done

echo ""
echo "Đã copy TLS + restart agent. Tiếp theo:"
echo "  - Commit/push cilium/clustermesh-management-peer.yaml + cilium/cilium-values.yaml (encryption) nếu Argo kéo từ Git."
echo "  - Sync app: cilium-dev, cilium-staging, cilium-prod (Argo) hoặc helm upgrade tương đương — để hostAliases + encryption khớp values."
echo "Kiểm hub: cilium clustermesh status --context ${HUB_CTX}"
