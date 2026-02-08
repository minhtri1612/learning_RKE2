#!/usr/bin/env bash
# Tạo ArgoCD Applications trên cluster management để deploy app xuống dev/prod.
# Chạy từ thư mục gốc project. Cần: terraform đã apply cho dev/prod; kubeconfig management; đã add clusters vào ArgoCD.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"
MGMT_DIR="$ROOT_DIR/argocd/environments/management"
# Use tunnel kubeconfig for local execution (connects via SSH tunnel to 127.0.0.1:6446)
KUBECONFIG_MGMT="$ROOT_DIR/.kube_config_rke2_management_tunnel.yaml"

cd "$ROOT_DIR"

# 1. Lấy cluster private IP từ terraform output (mỗi env)
# Sử dụng private IP thay vì NLB URL để match với cluster secrets
get_cluster_private_url() {
  local env="$1"
  local private_ip=$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -json 2>/dev/null | jq -r '.master_private_ip.value[0] // empty')
  if [[ -n "$private_ip" ]]; then
    echo "https://${private_ip}:6443"
  fi
}
PROD_URL="$(get_cluster_private_url prod)"
DEV_URL="$(get_cluster_private_url dev)"

if [[ -z "$PROD_URL" && -z "$DEV_URL" ]]; then
  echo "Lỗi: Không lấy được master_private_ip từ terraform. Chạy terraform apply cho ít nhất một env (dev/prod)."
  exit 1
fi

# 2. Tạo file tạm đã thay placeholder
TMP_DIR="$(mktemp -d)"
trap "rm -rf '$TMP_DIR'" EXIT
for f in "$MGMT_DIR"/*.yaml; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  # Use | as delimiter instead of / to avoid conflicts with URLs
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
