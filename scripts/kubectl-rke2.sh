#!/usr/bin/env bash
# Luôn dùng kube_config_rke2_<env>.yaml trong repo — tránh nhầm ~/.kube/config mặc định
# (API tới localhost:8080) khiến mọi lệnh kubectl / port-forward fail.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
  echo "Usage: $(basename "$0") <management|dev|prod> <kubectl args...>" >&2
  echo "Example: $(basename "$0") management get pods -n argocd" >&2
  exit 1
}

[[ "${1:-}" ]] || usage
ENV="$1"
shift

case "$ENV" in
  management|dev|prod) ;;
  *) echo "Unknown env: $ENV (expected management|dev|prod)" >&2; usage ;;
esac

export KUBECONFIG="${ROOT}/kube_config_rke2_${ENV}.yaml"
if [[ ! -f "$KUBECONFIG" ]]; then
  echo "Missing: $KUBECONFIG" >&2
  echo "  → Chạy provision.py cho env đó để fetch kubeconfig." >&2
  exit 1
fi

server="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || true)"
if [[ -z "$server" ]]; then
  echo "Cannot read cluster.server from $KUBECONFIG" >&2
  exit 1
fi
if [[ "$server" == *"localhost:8080"* ]] || [[ "$server" == *"127.0.0.1:8080"* ]]; then
  echo "ERROR: $KUBECONFIG points API to $server (không phải API RKE2 private trong repo)." >&2
  echo "  → Chạy lại provision.py để fetch kubeconfig; không merge kubeconfig localhost vào file này." >&2
  exit 1
fi

exec kubectl "$@"
