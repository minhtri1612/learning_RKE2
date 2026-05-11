#!/usr/bin/env bash
# Port-forward Argo CD trên cluster management (đúng KUBECONFIG repo, cổng local 8443).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "→ UI: https://localhost:8443 (chấp nhận cert). User: admin."
echo "→ argocd CLI (terminal khác): bash scripts/argocd-cli-login-local.sh"
echo "→ Giữ terminal này mở. Ctrl+C để dừng."
exec "$DIR/kubectl-rke2.sh" management port-forward svc/argocd-server -n argocd 8443:443
