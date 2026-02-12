#!/usr/bin/env bash
# Tạo ArgoCD Applications trên cluster management để deploy app xuống dev/prod.
# Updated: Sử dụng cấu trúc base + overlays
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"
CHART_DIR="$ROOT_DIR/argocd/applications/base"
OVERLAYS_DIR="$ROOT_DIR/argocd/applications/overlays"

# Use tunnel kubeconfig for local execution
KUBECONFIG_MGMT="$ROOT_DIR/.kube_config_rke2_management_tunnel.yaml"

cd "$ROOT_DIR"

# 1. Check Prerequisites
if ! [[ -f "$KUBECONFIG_MGMT" ]]; then
  echo "Chưa có $KUBECONFIG_MGMT. Chạy ./deploy.py management trước."
  exit 1
fi
export KUBECONFIG="$KUBECONFIG_MGMT"

# 2. Function to get cluster private URL
get_cluster_private_url() {
  local env="$1"
  local private_ip=$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -json 2>/dev/null | jq -r '.master_private_ip.value[0] // empty')
  if [[ -n "$private_ip" ]]; then
    echo "https://${private_ip}:6443"
  fi
}

PROD_URL="$(get_cluster_private_url prod)"
DEV_URL="$(get_cluster_private_url dev)"

echo "Target Cluster URLs:"
echo "  - Dev:  ${DEV_URL:-Not found (terraform output missing)}"
echo "  - Prod: ${PROD_URL:-Not found (terraform output missing)}"

# 3. Function to Render and Apply Helm Chart
apply_apps() {
    local env="$1"
    local url="$2"
    local values_file="$OVERLAYS_DIR/${env}/values.yaml"
    local placeholder="__CLUSTER_SERVER_${env^^}__" # e.g. __CLUSTER_SERVER_DEV__

    if [[ -n "$url" ]]; then
        echo "--- Deploying $env Applications (server: $url) ---"
        # Helm template with base + overlay values -> Replace Placeholder -> Kubectl Apply
        helm template applications "$CHART_DIR" \
            -f "$CHART_DIR/values.yaml" \
            -f "$values_file" | \
        sed "s|$placeholder|$url|g" | \
        kubectl apply -f -
    else
        echo "--- Skipping $env Applications (Cluster URL not found) ---"
    fi
}

# 4. Execute for each environment
apply_apps "dev" "$DEV_URL"
apply_apps "prod" "$PROD_URL"

echo ""
echo "Done. ArgoCD Applications have been updated via Helm Chart."
echo "Check UI: http://argocd.local"
