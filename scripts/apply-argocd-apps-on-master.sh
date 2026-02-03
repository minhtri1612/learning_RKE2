#!/usr/bin/env bash
# Chạy TRÊN MASTER NODE (sau khi đã ssh openvpn -> master).
# Cách 1: Clone repo rồi apply (cần git trên master)
#   git clone https://github.com/minhtri1612/learning_RKE2.git && cd learning_RKE2 && kubectl apply -f argocd/environments/dev/be-application.yaml && kubectl apply -f argocd/environments/dev/data-application.yaml
#
# Cách 2: Không cần git - tạo file inline rồi apply (copy-paste cả block vào terminal trên master)
# Chạy từng lệnh dưới đây trên master:

echo "Paste and run the following block ON THE MASTER (ubuntu@ip-10-0-101-137):"
echo "---"
cat << 'INLINE'
# Backend app
cat << 'EOF' | kubectl apply -f -
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
    server: https://kubernetes.default.svc
    namespace: meo-stationery
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - Replace=true
EOF

# Database app
cat << 'EOF' | kubectl apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-database-dev
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-options: Replace=true
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
    server: https://kubernetes.default.svc
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
INLINE
