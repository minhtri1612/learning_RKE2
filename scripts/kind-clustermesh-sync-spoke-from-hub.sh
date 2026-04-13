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

# CA mỗi cluster Kind thường khác nhau. Ghép CA spoke vào management (client trust bundle)
# và ghép CA management vào server trust bundle của spoke để mTLS 2 chiều hoạt động.
echo "==> Đồng bộ CA bundle 2 chiều (management <-> spoke)"
CA_BUNDLE="$(mktemp)"
trap 'rm -f "${TMP}" "${CA_BUNDLE}" /tmp/cm-mgmt-ca.pem /tmp/cm-spoke-ca.pem /tmp/cm-spoke-bundle.pem' EXIT
kubectl --context "${HUB_CTX}" -n "${HUB_NS}" get secret clustermesh-apiserver-remote-cert -o jsonpath='{.data.ca\.crt}' | base64 -d > "${CA_BUNDLE}"
echo >> "${CA_BUNDLE}"
for ctx in kind-dev kind-staging kind-prod; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  kubectl --context "${ctx}" -n "${HUB_NS}" get secret clustermesh-apiserver-remote-cert -o jsonpath='{.data.ca\.crt}' | base64 -d >> "${CA_BUNDLE}"
  echo >> "${CA_BUNDLE}"
done
kubectl --context "${HUB_CTX}" -n "${HUB_NS}" patch secret clustermesh-apiserver-remote-cert \
  --type=merge -p "{\"data\":{\"ca.crt\":\"$(base64 -w0 "${CA_BUNDLE}")\"}}"
kubectl --context "${HUB_CTX}" -n "${HUB_NS}" rollout restart ds/cilium deploy/clustermesh-apiserver >/dev/null

for ctx in kind-dev kind-staging kind-prod; do
  if ! kubectl config get-contexts -o name | grep -qx "${ctx}"; then
    echo "Bỏ qua (không có context): ${ctx}"
    continue
  fi
  echo "==> ${ctx}: apply ${SECRET_NAME} + rollout restart ds/cilium"
  kubectl --context "${ctx}" -n "${HUB_NS}" apply -f "${TMP}"
  # Spoke server cần trust CA của management để xác thực client cert từ KVStoreMesh hub.
  kubectl --context "${HUB_CTX}" -n "${HUB_NS}" get secret clustermesh-apiserver-remote-cert -o jsonpath='{.data.ca\.crt}' | base64 -d > /tmp/cm-mgmt-ca.pem
  kubectl --context "${ctx}" -n "${HUB_NS}" get secret clustermesh-apiserver-server-cert -o jsonpath='{.data.ca\.crt}' | base64 -d > /tmp/cm-spoke-ca.pem
  cat /tmp/cm-spoke-ca.pem /tmp/cm-mgmt-ca.pem > /tmp/cm-spoke-bundle.pem
  kubectl --context "${ctx}" -n "${HUB_NS}" patch secret clustermesh-apiserver-server-cert \
    --type=merge -p "{\"data\":{\"ca.crt\":\"$(base64 -w0 /tmp/cm-spoke-bundle.pem)\"}}"
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout restart deploy/clustermesh-apiserver >/dev/null 2>&1 || true
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout restart ds/cilium
done

for ctx in kind-dev kind-staging kind-prod; do
  kubectl config get-contexts -o name | grep -qx "${ctx}" || continue
  kubectl --context "${ctx}" -n "${HUB_NS}" rollout status ds/cilium --timeout=180s
done

echo ""
echo "Đã copy TLS + restart agent. Tiếp theo:"
echo "  - Hub: cilium-values-management.yaml phải có clustermesh.config.clusters (dev/staging/prod) — không thì"
echo "    Secret cilium-clustermesh trên management rỗng và 'cilium clustermesh status' luôn 'No cluster connected'."
echo "  - Commit/push + Sync Argo: cilium-management trước, rồi cilium-dev/staging/prod; hoặc helm upgrade tương đương."
echo "  - Sau khi hub sync: kubectl --context ${HUB_CTX} -n ${HUB_NS} rollout restart ds/cilium"
echo "Kiểm: cilium clustermesh status --context ${HUB_CTX}"
