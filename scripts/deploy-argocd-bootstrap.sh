#!/usr/bin/env bash
# Deploy ArgoCD Bootstrap (ApplicationSets pattern)
# Replaces old setup-argocd-management-apps.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use tunnel kubeconfig for local execution
KUBECONFIG_MGMT="$ROOT_DIR/.kube_config_rke2_management_tunnel.yaml"

if ! [[ -f "$KUBECONFIG_MGMT" ]]; then
  echo "Error: $KUBECONFIG_MGMT not found. Run ./deploy.py management first."
  exit 1
fi

export KUBECONFIG="$KUBECONFIG_MGMT"

echo "=== ArgoCD Bootstrap Deployment ==="
echo ""
echo "1. Applying ArgoCD Projects..."
kubectl apply -f "$ROOT_DIR/argocd/projects/"

echo ""
echo "2. Applying ArgoCD RBAC..."
kubectl apply -f "$ROOT_DIR/argocd/rbac/"

echo ""
echo "3. Applying Root App (ApplicationSets)..."
kubectl apply -f "$ROOT_DIR/argocd/bootstrap/root-app.yaml"

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "ApplicationSets deployed:"
kubectl get applicationsets -n argocd
echo ""
echo "Generated Applications (may take 10-30s):"
kubectl get applications -n argocd
echo ""
echo "Check UI: http://argocd.local"
