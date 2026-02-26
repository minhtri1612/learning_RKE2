#!/usr/bin/env bash
# Khắc phục "revision main must be resolved" + 404 dev/prod trong một lần chạy.
# Chạy khi đã BẬT VPN. Cần: kubeconfig management + dev + prod.
#
# Nguyên nhân thường gặp:
# - "revision main must be resolved": ArgoCD không fetch được branch main từ Git
#   (repo private chưa cấu hình credentials, hoặc repo/branch sai, hoặc file YAML trong repo bị lỗi)
# - 404: cluster secret IP sai, hoặc webhook ingress chưa xóa, hoặc app chưa sync
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

MGMT_KUBECONFIG="${MGMT_KUBECONFIG:-$ROOT_DIR/kube_config_rke2_management.yaml}"

echo "=============================================="
echo "  FIX ArgoCD (revision main) + 404 dev/prod"
echo "=============================================="
echo ""

# --- 1. Kiểm tra YAML cluster (tránh push file lỗi lên Git)
echo "=== 1. Kiểm tra YAML argocd/clusters (tránh push file lỗi) ==="
YAML_BAD=""
for f in argocd/clusters/cluster-dev.yaml argocd/clusters/cluster-prod.yaml; do
  if [[ -f "$f" ]]; then
    if python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null; then
      echo "  ✓ $f valid"
    else
      echo "  ✗ $f INVALID YAML"
      YAML_BAD=1
    fi
  fi
done
if [[ -n "$YAML_BAD" ]]; then
  echo "  → Sửa: bash scripts/create-argocd-cluster-secrets.sh dev && bash scripts/create-argocd-cluster-secrets.sh prod"
  echo "  → Rồi chạy lại script này. Đang tiếp tục..."
fi
echo ""

# --- 2. Repo ArgoCD vs remote hiện tại
echo "=== 2. Repo ArgoCD dùng vs Git remote của thư mục này ==="
ARGOCD_REPO=$(grep -m1 "repoURL:" argocd/bootstrap/02-root-app.yaml | sed 's/.*repoURL: *//' | tr -d ' ')
echo "  ArgoCD repo: $ARGOCD_REPO"
echo "  Git remote:  $(git remote get-url origin 2>/dev/null || echo '(không có)')"
if [[ -n "$ARGOCD_REPO" ]] && ! git remote -v 2>/dev/null | grep -q "$ARGOCD_REPO"; then
  echo "  ⚠ Khác repo! ArgoCD chỉ đọc từ $ARGOCD_REPO — phải push branch main lên đó (hoặc đổi ArgoCD sang repo của thư mục này)."
fi
echo ""

# --- 3. Push thay đổi (cluster YAML đã fix) lên Git
echo "=== 3. Push argocd/clusters lên Git (để ArgoCD đọc được revision main) ==="
if git status --porcelain argocd/clusters/ 2>/dev/null | grep -q .; then
  git add argocd/clusters/
  git commit -m "fix: argocd cluster manifests (valid YAML)" || true
  git push
  echo "  ✓ Đã push."
else
  echo "  ⏭ Không có thay đổi argocd/clusters — bỏ qua push."
fi
echo ""

# --- 4. Apply cluster secret lên management (IP đúng từ kubeconfig)
echo "=== 4. Apply ArgoCD cluster secrets trên management (IP từ kubeconfig) ==="
if [[ ! -f "$MGMT_KUBECONFIG" ]]; then
  echo "  ⚠ Không có $MGMT_KUBECONFIG — bỏ qua."
else
  export KUBECONFIG="$MGMT_KUBECONFIG"
  bash "$SCRIPT_DIR/create-argocd-cluster-secrets.sh" dev
  bash "$SCRIPT_DIR/create-argocd-cluster-secrets.sh" prod
  echo "  ✓ Cluster secrets đã cập nhật."
fi
echo ""

# --- 5. Xóa webhook ingress-nginx trên dev và prod (để Ingress apply được)
echo "=== 5. Xóa webhook ingress-nginx (dev + prod) ==="
for env in dev prod; do
  bash "$SCRIPT_DIR/fix-ingress-nginx-webhook.sh" "$env" 2>/dev/null || true
done
echo ""

# --- 6. Refresh ArgoCD apps (ép đọc lại Git)
echo "=== 6. Refresh ArgoCD apps (ép resolve lại revision main) ==="
if [[ -f "$MGMT_KUBECONFIG" ]]; then
  export KUBECONFIG="$MGMT_KUBECONFIG"
  for app in argocd-clusters root-appsets meo-station-backend-dev meo-station-backend-prod meo-station-database-dev meo-station-database-prod; do
    kubectl patch application "$app" -n argocd --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' 2>/dev/null && echo "  ✓ Refreshed $app" || true
  done
  echo "  Gợi ý: Vào ArgoCD UI → từng app → REFRESH (Hard Refresh) rồi SYNC nếu vẫn báo lỗi."
fi
echo ""

echo "=============================================="
echo "  Nếu vẫn 'revision main must be resolved':"
echo "  - Repo private: thêm credentials vào argocd/repositories/repo-credentials.yaml (username + password/token) rồi apply lên management."
echo "  - Kiểm tra branch: GitHub repo có branch 'main' không? (ArgoCD đang dùng targetRevision: main)"
echo "  - ArgoCD UI → Application → APP DETAILS: xem lỗi chi tiết (Comparison Error / Sync Error)."
echo "=============================================="
echo "  Nếu vẫn 404: vào ArgoCD bấm SYNC cho meo-station-backend-dev/prod và meo-station-database-dev/prod."
echo "=============================================="
