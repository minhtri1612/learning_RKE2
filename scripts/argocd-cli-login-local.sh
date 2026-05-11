#!/usr/bin/env bash
# Đăng nhập argocd CLI vào server đang port-forward (mặc định https://127.0.0.1:8443).
# Chạy SAU khi đã: bash scripts/argocd-ui-forward.sh (terminal khác giữ forward mở).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTPORT="${1:-127.0.0.1:8443}"

pass="$("$DIR/kubectl-rke2.sh" management get secret -n argocd argocd-initial-admin-secret -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"
if [[ -z "$pass" ]]; then
  echo "Không đọc được argocd-initial-admin-secret (đã xóa sau đổi pass?). Nhập password admin tay:" >&2
  read -r -s pass
  echo
fi

echo "→ argocd login $HOSTPORT (user admin, --insecure)"
exec argocd login "$HOSTPORT" --username admin --password "$pass" --insecure
