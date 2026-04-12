#!/usr/bin/env bash
# Trỏ kubeconfig các context Kind sang 127.0.0.1 (tránh server 0.0.0.0 → lỗi TLS với API).
# Dùng sau kind create; management phải chạy (hoặc tương đương) *trước* helm install cilium — xem kind/KIND-THREE-CLUSTERS.md mục 1.2.
set -euo pipefail
kubectl config set-cluster kind-management --server=https://127.0.0.1:33443
kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
kubectl config set-cluster kind-staging --server=https://127.0.0.1:32443
kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
echo "OK: kind-management/dev/staging/prod → 127.0.0.1 (33443 / 30443 / 32443 / 31443)."
