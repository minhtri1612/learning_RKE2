#!/usr/bin/env bash
# Sync CA bundle cho ClusterMesh mTLS giữa 4 cluster Kind (management + dev/staging/prod).
# Mỗi cluster Kind có CA riêng → cần bundle TẤT CẢ CA vào cả remote-cert và server-cert
# trên MỌI cluster để mTLS 2 chiều hoạt động.
#
# Script này: (1) ghi IP hub vào cilium/clustermesh-management-peer.yaml
#              (2) thu thập cilium-ca từ tất cả cluster → tạo universal bundle
#              (3) patch remote-cert + server-cert trên MỌI cluster với bundle đó
#              (4) restart clustermesh-apiserver + cilium trên mọi cluster
#
# Sau đó cần sync Helm/Argo để DaemonSet nhận hostAliases + encryption từ Git (xem cuối script).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HUB_CTX="${HUB_CTX:-kind-management}"
HUB_NS="${HUB_NS:-kube-system}"
SPOKE_CTXS=("kind-dev" "kind-staging" "kind-prod")
ALL_CTXS=("${HUB_CTX}" "${SPOKE_CTXS[@]}")
PEER_SCRIPT="${ROOT}/scripts/kind-clustermesh-peer-ip.sh"

if [[ ! -f "${PEER_SCRIPT}" ]]; then
  echo "Thiếu ${PEER_SCRIPT}" >&2
  exit 1
fi

echo "==> Cập nhật IP hub -> cilium/clustermesh-management-peer.yaml"
bash "${PEER_SCRIPT}"

if ! kubectl --context "${HUB_CTX}" get secret -n "${HUB_NS}" clustermesh-apiserver-remote-cert &>/dev/null; then
  echo "Lỗi: trên hub (${HUB_CTX}) chưa có secret clustermesh-apiserver-remote-cert. Kiểm tra Cilium ClusterMesh trên management." >&2
  exit 1
fi

CA_ALL="$(mktemp)"
trap 'rm -f "${CA_ALL}"' EXIT

echo "==> Thu thập cilium-ca từ tất cả cluster"
for ctx in "${ALL_CTXS[@]}"; do
  if ! kubectl config get-contexts -o name | grep -qx "${ctx}"; then
    echo "  Bỏ qua (không có context): ${ctx}"
    continue
  fi
  kubectl --context "${ctx}" -n "${HUB_NS}" get secret cilium-ca -o jsonpath='{.data.ca\.crt}' | base64 -d >> "${CA_ALL}"
  echo >> "${CA_ALL}"
  echo "  ✓ ${ctx}"
done

CA_B64="$(base64 -w0 "${CA_ALL}")"

echo "==> Patch remote-cert + server-cert trên TẤT CẢ cluster với universal CA bundle"
for ctx in "${ALL_CTXS[@]}"; do
  if ! kubectl config get-contexts -o name | grep -qx "${ctx}"; then
    echo "  Bỏ qua (không có context): ${ctx}"
    continue
  fi
  echo "  === ${ctx} ==="
  kubectl --context "${ctx}" -n "${HUB_NS}" patch secret clustermesh-apiserver-remote-cert \
    --type=merge -p "{\"data\":{\"ca.crt\":\"${CA_B64}\"}}"
  kubectl --context "${ctx}" -n "${HUB_NS}" patch secret clustermesh-apiserver-server-cert \
    --type=merge -p "{\"data\":{\"ca.crt\":\"${CA_B64}\"}}"
done

echo "==> Restart clustermesh-apiserver + cilium trên tất cả cluster"
for ctx in "${ALL_CTXS[@]}"; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  echo "  === ${ctx} ==="
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout restart deploy/clustermesh-apiserver ds/cilium
done

echo "==> Đợi cilium DaemonSet rollout..."
for ctx in "${ALL_CTXS[@]}"; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout status ds/cilium --timeout=180s
done

echo ""
echo "✅ Đã sync CA bundle + restart tất cả cluster. Tiếp theo:"
echo "  - Commit/push + Sync Argo: cilium-management trước, rồi cilium-dev/staging/prod."
echo "  - Kiểm: for ctx in kind-management kind-dev kind-staging kind-prod; do cilium clustermesh status --context \$ctx; done"
