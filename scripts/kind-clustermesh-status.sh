#!/usr/bin/env bash
# Kiểm tra ClusterMesh trên mọi context Kind (cần cilium CLI: cilium clustermesh status).
set -euo pipefail
CTXS=(kind-management kind-dev kind-staging kind-prod)
for ctx in "${CTXS[@]}"; do
  echo "======== ${ctx} ========"
  if ! kubectl config get-contexts -o name 2>/dev/null | grep -qx "${ctx}"; then
    echo "(bỏ qua — không có context ${ctx})"
    continue
  fi
  if command -v cilium >/dev/null 2>&1; then
    cilium clustermesh status --context "${ctx}" 2>&1 || true
  else
    echo "Chưa cài cilium CLI — chỉ kiểm tra pod clustermesh-apiserver trên management:"
    kubectl --context kind-management -n kube-system get pods -l name=clustermesh-apiserver 2>/dev/null || true
    break
  fi
done
