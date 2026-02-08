#!/usr/bin/env bash
# Add dev/prod clusters to ArgoCD from Management Kubernetes master
# This script runs ON the Management master server where kubectl is available

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Get Management master IP from terraform
MGMT_MASTER_IP=$(cd "$ROOT_DIR/terraform" && terraform -chdir="environments/management" output -json 2>/dev/null | jq -r '.master_private_ip.value[0] // empty')

if [[ -z "$MGMT_MASTER_IP" ]]; then
  echo "Error: Cannot get management master IP"
  exit 1
fi

echo "Management Master IP: $MGMT_MASTER_IP"
echo "Installing ArgoCD CLI and adding clusters..."

# SSH key for Management server
MGMT_KEY="$ROOT_DIR/terraform/environments/management/k8s-key.pem"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes"

# Install ArgoCD CLI on Management master (if not already installed)
ssh -i "$MGMT_KEY" $SSH_OPTS "ubuntu@${MGMT_MASTER_IP}" 'bash -s' <<'REMOTE_SCRIPT'
set -e

# Install ArgoCD CLI if needed
if ! command -v argocd &> /dev/null; then
  echo "Installing ArgoCD CLI..."
  curl -sSL -o /tmp/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
  sudo install -m 555 /tmp/argocd /usr/local/bin/argocd
  rm /tmp/argocd
fi

# Get ArgoCD password
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)

# Setup port-forward to ArgoCD server (argocd.local won't resolve on master)
echo "Setting up port-forward to ArgoCD..."
kubectl port-forward svc/argocd-server -n argocd 8080:443 > /dev/null 2>&1 &
PF_PID=$!
trap "kill $PF_PID 2>/dev/null || true" EXIT
sleep 3

# Login to ArgoCD via localhost
argocd login localhost:8080 --insecure --username admin --password "$ARGOCD_PASSWORD"

echo "Adding clusters to ArgoCD..."

# Dev cluster
DEV_MASTER_IP="10.1.101.10"
PROD_MASTER_IP="10.2.101.103"

for env in dev prod; do
  if [[ "$env" == "dev" ]]; then
    MASTER_IP="$DEV_MASTER_IP"
  else
    MASTER_IP="$PROD_MASTER_IP"
  fi
  
  echo "Processing $env cluster ($MASTER_IP)..."
  
  # Fetch kubeconfig from target master
  ssh -i ~/.ssh/k8s-key-${env}.pem -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@"${MASTER_IP}" \
    "sudo cat /etc/rancher/rke2/rke2.yaml" > "/tmp/kubeconfig-${env}.yaml"
  
  # Update server URL to use private IP
  sed -i "s|https://127.0.0.1:6443|https://${MASTER_IP}:6443|g" "/tmp/kubeconfig-${env}.yaml"
  
  # Add cluster to ArgoCD
  KUBECONFIG="/tmp/kubeconfig-${env}.yaml" argocd cluster add default --name "${env}" --yes || echo "Cluster ${env} may already exist"
  
  echo "  ✓ $env cluster added"
done

echo "Done! Clusters registered in ArgoCD."
argocd cluster list

REMOTE_SCRIPT

echo ""
echo "Clusters added successfully! Check ArgoCD UI to verify."
