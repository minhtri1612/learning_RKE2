#!/usr/bin/env bash
# Quick setup ArgoCD Applications - chạy từ OpenVPN, kubectl trên master
set -e

echo "===== Quick ArgoCD Applications Setup ====="

MGMT_MASTER="10.0.101.80"
DEV_MASTER="10.1.101.246"
PROD_MASTER="10.2.101.212"

DEV_URL="https://${DEV_MASTER}:6443"
PROD_URL="https://${PROD_MASTER}:6443"

echo "Dev cluster: $DEV_URL"
echo "Prod cluster: $PROD_URL"
echo ""
echo "Creating Applications via kubectl on master..."

# Chạy kubectl trên master node (master có kubectl sẵn)
ssh -i ~/.ssh/k8s-key.pem ubuntu@$MGMT_MASTER bash <<'REMOTE_CMD'
export KUBECONFIG=~/.kube/config

# Backend Dev
kubectl apply -f - <<EOF
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
    server: https://10.1.101.246:6443
    namespace: meo-stationery
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
EOF
echo "✓ backend-dev created"

# Database Dev
kubectl apply -f - <<EOF
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
    server: https://10.1.101.246:6443
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
echo "✓ database-dev created"

# Backend Prod
kubectl apply -f - <<EOF
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
    server: https://10.2.101.212:6443
    namespace: meo-stationery
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
EOF
echo "✓ backend-prod created"

# Database Prod
kubectl apply -f - <<EOF
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
    server: https://10.2.101.212:6443
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
echo "✓ database-prod created"

echo ""
echo "Verify applications:"
kubectl get applications -n argocd
REMOTE_CMD

echo ""
echo "===== Done ====="
echo "Check ArgoCD UI: http://argocd.local"
