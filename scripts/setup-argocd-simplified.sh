#!/usr/bin/env bash
# Simplified ArgoCD setup - all from local machine
set -e

PROJECT_ROOT="/home/minhtri/Downloads/practice_RKE2"
cd "$PROJECT_ROOT"

echo "===== Simplified ArgoCD Multi-Cluster Setup ====="
echo ""

# Step 1: Install ArgoCD CLI if needed
if ! command -v argocd &>/dev/null; then
    echo "Step 1: Installing ArgoCD CLI..."
    curl -sSL -o /tmp/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
    chmod +x /tmp/argocd
    sudo mv /tmp/argocd /usr/local/bin/
    echo "✓ ArgoCD CLI installed"
else
    echo "✓ ArgoCD CLI already installed"
fi

# Step 2: Get cluster API URLs from terraform
echo ""
echo "Step 2: Getting cluster API URLs..."
DEV_URL=$(cd terraform && terraform -chdir=environments/dev output -raw cluster_api_url 2>/dev/null) || DEV_URL=""
PROD_URL=$(cd terraform && terraform -chdir=environments/prod output -raw cluster_api_url 2>/dev/null) || PROD_URL=""

echo "Dev cluster URL: ${DEV_URL:-NOT FOUND}"
echo "Prod cluster URL: ${PROD_URL:-NOT FOUND}"

if [[ -z "$DEV_URL" && -z "$PROD_URL" ]]; then
    echo "⚠ No cluster API URLs found. Make sure terraform has been applied for dev/prod."
    exit 1
fi

# Step 3: Get ArgoCD password (via HTTP API since kubectl times out)
echo ""
echo "Step 3: Getting ArgoCD admin password via port-forward..."
# Start temporary port-forward to ArgoCD
pkill -f 'kubectl port-forward.*argocd-server' 2>/dev/null || true
sleep 2

export KUBECONFIG="$PROJECT_ROOT/.kube_config_rke2_management_tunnel.yaml"
kubectl port-forward svc/argocd-server -n argocd 8080:443 &>/tmp/argocd-pf.log &
PF_PID=$!
sleep 5

# Try to get password via kubectl
ARGOCD_PASSWORD=$(kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' 2>/dev/null | base64 -d) || ARGOCD_PASSWORD=""

if [[ -z "$ARGOCD_PASSWORD" ]]; then
    echo "⚠ Could not get password automatically. Please get it manually:"
    echo "   kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d"
    kill $PF_PID 2>/dev/null || true
    exit 1
fi

echo "✓ ArgoCD Password: $ARGOCD_PASSWORD"

# Step 4: Login to ArgoCD
echo ""
echo "Step 4: Login to ArgoCD..."
argocd login localhost:8080 --insecure --username admin --password "$ARGOCD_PASSWORD" --grpc-web

# Step 5: Add dev cluster
if [[ -n "$DEV_URL" ]]; then
    echo ""
    echo "Step 5a: Adding dev cluster..."
    if argocd cluster add default --name dev --kubeconfig "$PROJECT_ROOT/kube_config_rke2_dev.yaml" --yes --grpc-web 2>&1 | grep -qi "already exists"; then
        echo "✓ Dev cluster already registered"
    else
        echo "✓ Dev cluster added"
    fi
    
    # Patch server URL to use NLB
    echo "Patching dev cluster server URL to NLB..."
    DEV_SECRET=$(kubectl get secrets -n argocd -l argocd.argoproj.io/secret-type=cluster -o json | jq -r '.items[] | select(.data.name != null) | select((.data.name | @base64d) == "dev") | .metadata.name')
    if [[ -n "$DEV_SECRET" ]]; then
        DEV_SERVER_B64=$(echo -n "$DEV_URL" | base64 -w 0)
        kubectl patch secret -n argocd "$DEV_SECRET" -p "{\"data\":{\"server\":\"$DEV_SERVER_B64\"}}"
        echo "✓ Dev cluster server patched to NLB"
    fi
fi

# Step 6: Add prod cluster
if [[ -n "$PROD_URL" ]]; then
    echo ""
    echo "Step 6: Adding prod cluster..."
    if argocd cluster add default --name prod --kubeconfig "$PROJECT_ROOT/kube_config_rke2_prod.yaml" --yes --grpc-web 2>&1 | grep -qi "already exists"; then
        echo "✓ Prod cluster already registered"
    else
        echo "✓ Prod cluster added"
    fi
    
    # Patch server URL to use NLB
    echo "Patching prod cluster server URL to NLB..."
    PROD_SECRET=$(kubectl get secrets -n argocd -l argocd.argoproj.io/secret-type=cluster -o json | jq -r '.items[] | select(.data.name != null) | select((.data.name | @base64d) == "prod") | .metadata.name')
    if [[ -n "$PROD_SECRET" ]]; then
        PROD_SERVER_B64=$(echo -n "$PROD_URL" | base64 -w 0)
        kubectl patch secret -n argocd "$PROD_SECRET" -p "{\"data\":{\"server\":\"$PROD_SERVER_B64\"}}"
        echo "✓ Prod cluster server patched to NLB"
    fi
fi

# Step 7: Create Application manifests
echo ""
echo "Step 7: Creating ArgoCD Applications..."

# Create backend-dev
if [[ -n "$DEV_URL" ]]; then
    cat <<EOF | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-backend-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/minhtri1612/learning_RKE2.git
    targetRevision: main
    path: k8s_helm/backend
    helm:
      valueFiles:
        - values.yaml
        - values-dev.yaml
  destination:
    server: $DEV_URL
    namespace: meo-stationery
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
EOF
    echo "✓ backend-dev application created"

    # Create database-dev
    cat <<EOF | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-database-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/minhtri1612/learning_RKE2.git
    targetRevision: main
    path: k8s_helm/database
    helm:
      valueFiles:
        - values.yaml
        - values-dev.yaml
  destination:
    server: $DEV_URL
    namespace: database
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
  ignoreDifferences:
  - group: apps
    kind: StatefulSet
    jsonPointers:
    - /spec/volumeClaimTemplates
    - /spec/serviceName
EOF
    echo "✓ database-dev application created"
fi

# Create backend-prod
if [[ -n "$PROD_URL" ]]; then
    cat <<EOF | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-backend-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/minhtri1612/learning_RKE2.git
    targetRevision: main
    path: k8s_helm/backend
    helm:
      valueFiles:
        - values.yaml
        - values-prod.yaml
  destination:
    server: $PROD_URL
    namespace: meo-stationery
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
EOF
    echo "✓ backend-prod application created"

    # Create database-prod
    cat <<EOF | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-database-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/minhtri1612/learning_RKE2.git
    targetRevision: main
    path: k8s_helm/database
    helm:
      valueFiles:
        - values.yaml
        - values-prod.yaml
  destination:
    server: $PROD_URL
    namespace: database
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
  ignoreDifferences:
  - group: apps
    kind: StatefulSet
    jsonPointers:
    - /spec/volumeClaimTemplates
    - /spec/serviceName
EOF
    echo "✓ database-prod application created"
fi

# Clean up port-forward
kill $PF_PID 2>/dev/null || true

echo ""
echo "===== Setup Complete ====="
echo "ArgoCD UI: http://argocd.local"
echo "Username: admin"
echo "Password: $ARGOCD_PASSWORD"
echo ""
echo "Verify:"
echo "  - Open http://argocd.local"
echo "  - Settings -> Clusters (should see dev and prod)"
echo "  - Applications (should see 4 apps syncing)"
