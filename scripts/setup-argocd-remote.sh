#!/usr/bin/env bash
# Execute ArgoCD setup scripts on management cluster (simpler than local tunneling issues)
set -e

MGMT_IP="13.238.133.49"  # Management OpenVPN IP
KEY="/home/minhtri/Downloads/practice_RKE2/terraform/environments/management/k8s-key.pem"
REPO_DIR="/home/minhtri/Downloads/practice_RKE2"

echo "===== ArgoCD Multi-Cluster Setup via Management Cluster ====="
echo ""
echo "Step 1: Copy project files to management cluster..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP 'mkdir -p ~/practice_RKE2'
scp -i "$KEY" -o StrictHostKeyChecking=no -r "$REPO_DIR/scripts" "ubuntu@$MGMT_IP:~/practice_RKE2/"
scp -i "$KEY" -o StrictHostKeyChecking=no -r "$REPO_DIR/argocd" "ubuntu@$MGMT_IP:~/practice_RKE2/"
scp -i "$KEY" -o StrictHostKeyChecking=no -r "$REPO_DIR/terraform" "ubuntu@$MGMT_IP:~/practice_RKE2/"
scp -i "$KEY" -o StrictHostKeyChecking=no "$REPO_DIR"/kube_config_rke2*.yaml "ubuntu@$MGMT_IP:~/practice_RKE2/"

echo ""
echo "Step 2: Install prerequisites on management cluster..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP 'bash -s' << 'INSTALL_DEPS'
set -e
# Install ArgoCD CLI
if ! command -v argocd &>/dev/null; then
  echo "Installing ArgoCD CLI..."
  curl -sSL -o /tmp/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
  chmod +x /tmp/argocd
  sudo mv /tmp/argocd /usr/local/bin/
  echo "✓ ArgoCD CLI installed"
fi

# Install jq if not present
if ! command -v jq &>/dev/null; then
  echo "Installing jq..."
  sudo apt-get update -qq && sudo apt-get install -y jq
  echo "✓ jq installed"
fi

# Install terraform if not present
if ! command -v terraform &>/dev/null; then
  echo "Installing terraform..."
  wget -q https://releases.hashicorp.com/terraform/1.6.6/terraform_1.6.6_linux_amd64.zip
  unzip -q terraform_1.6.6_linux_amd64.zip
  sudo mv terraform /usr/local/bin/
  rm terraform_1.6.6_linux_amd64.zip
  echo "✓ terraform installed"
fi

echo "All prerequisites installed"
INSTALL_DEPS

echo ""
echo "Step 3: Get ArgoCD admin password..."
ARGOCD_PASSWORD=$(ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP \
  'export KUBECONFIG=~/practice_RKE2/kube_config_rke2_management.yaml && \
   kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d')

if [[ -z "$ARGOCD_PASSWORD" ]]; then
  echo "⚠ Could not get ArgoCD password. Trying alternative method..."
  ARGOCD_PASSWORD=$(ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP \
    'sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d')
fi

echo "✓ ArgoCD Password: $ARGOCD_PASSWORD"
echo ""

echo "Step 4: Register clusters in ArgoCD..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP \
  "export ARGOCD_PASSWORD='$ARGOCD_PASSWORD' && cd ~/practice_RKE2 && bash scripts/argocd-add-clusters.sh"

echo ""
echo "Step 5: Deploy ArgoCD Applications..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@$MGMT_IP \
  "cd ~/practice_RKE2 && bash scripts/setup-argocd-management-apps.sh"

echo ""
echo "===== Setup Complete ====="
echo "ArgoCD UI: http://argocd.local"
echo "Username: admin"
echo "Password: $ARGOCD_PASSWORD"
echo ""
echo "Verify in ArgoCD UI:"
echo "  - Settings -> Clusters (should see dev and prod)"
echo "  - Applications (should see backend-dev, database-dev, backend-prod, database-prod)"
