#!/usr/bin/env bash
# Tạo ArgoCD Applications trên cluster management để deploy app xuống dev/prod.
# Chạy từ thư mục gốc project. Cần: terraform đã apply cho dev/prod; kubeconfig management; đã add clusters vào ArgoCD.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"
MGMT_DIR="$ROOT_DIR/argocd/environments/management"
KUBECONFIG_MGMT="$ROOT_DIR/kube_config_rke2_management.yaml"

cd "$ROOT_DIR"

# 1. Lấy cluster API URL từ terraform output (mỗi env)
get_cluster_url() {
  local env="$1"
  (cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -raw cluster_api_url 2>/dev/null) || true
}
PROD_URL="$(get_cluster_url prod)"
DEV_URL="$(get_cluster_url dev)"

if [[ -z "$PROD_URL" && -z "$DEV_URL" ]]; then
  echo "Lỗi: Không lấy được cluster_api_url từ terraform. Chạy terraform apply cho ít nhất một env (dev/prod)."
  exit 1
fi

# 2. Tạo file tạm đã thay placeholder
TMP_DIR="$(mktemp -d)"
trap "rm -rf '$TMP_DIR'" EXIT
for f in "$MGMT_DIR"/*.yaml; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  sed -e "s|__CLUSTER_SERVER_PROD__|${PROD_URL:-__CLUSTER_SERVER_PROD__}|g" \
      -e "s|__CLUSTER_SERVER_DEV__|${DEV_URL:-__CLUSTER_SERVER_DEV__}|g" \
      "$f" > "$TMP_DIR/$name"
  # Bỏ qua Application nếu server vẫn là placeholder (env chưa có terraform)
  if grep -q '__CLUSTER_SERVER_' "$TMP_DIR/$name"; then
    echo "Bỏ qua $name (chưa có cluster_api_url cho env tương ứng)"
    rm -f "$TMP_DIR/$name"
  fi
done

# 3. Apply lên cluster management
if ! [[ -f "$KUBECONFIG_MGMT" ]]; then
  echo "Chưa có $KUBECONFIG_MGMT. Chạy ./deploy.py management trước."
  exit 1
fi
export KUBECONFIG="$KUBECONFIG_MGMT"
count="$(find "$TMP_DIR" -maxdepth 1 -name '*.yaml' 2>/dev/null | wc -l)"
if [[ "$count" -eq 0 ]]; then
  echo "Không có Application nào để apply (cần terraform output cluster_api_url cho ít nhất một env)."
  exit 0
fi
kubectl apply -f "$TMP_DIR"
echo "Done. ArgoCD Applications đã apply lên cluster management. Mở http://argocd.local để xem."
echo "Nếu cluster chưa được add vào ArgoCD, chạy: ARGOCD_PASSWORD=<pass> ./scripts/argocd-add-clusters.sh"
