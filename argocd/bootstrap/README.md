# ArgoCD Bootstrap

Bootstrap ArgoCD using ApplicationSets pattern for enterprise-scale deployments.

## Architecture

```
Bootstrap (one-time setup)
    ↓
Root ApplicationSet App
    ↓
ApplicationSets (auto-generate Applications)
    ↓
Applications (backend-dev, backend-prod, database-dev, database-prod, etc.)
    ↓
Kubernetes Resources
```

## Initial Setup

### 1. Install ArgoCD (one-time)

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm install argocd argo/argo-cd \
  -f argocd/bootstrap/argocd-install.yaml \
  -n argocd --create-namespace
```

### 2. Apply ArgoCD Projects

```bash
kubectl apply -f argocd/projects/
```

Projects created:
- `dev` - Development environment
- `staging` - Staging environment (future)
- `prod` - Production environment
- `infrastructure` - Infrastructure apps (ESO, monitoring, etc.)

### 3. Apply RBAC Configuration

```bash
kubectl apply -f argocd/rbac/
```

### 4. Bootstrap Root App (GitOps starts here)

```bash
kubectl apply -f argocd/bootstrap/root-app.yaml
```

This creates:
- `root-appsets` - Syncs ApplicationSets from Git
- `argocd-notifications` - Syncs notification config

### 5. Verify ApplicationSets Created

```bash
kubectl get applicationset -n argocd
```

Expected output:
```
NAME              AGE
applications      1m
infrastructure    1m
```

### 6. Verify Applications Auto-Generated

```bash
kubectl get applications -n argocd
```

Expected output:
```
NAME                          SYNC STATUS   HEALTH STATUS
meo-station-backend-dev       Synced        Healthy
meo-station-backend-prod      Synced        Healthy
meo-station-database-dev      Synced        Healthy
meo-station-database-prod     Synced        Healthy
```

## Adding New Services

### Add to ApplicationSet

Edit `argocd/appsets/appset-applications.yaml`:

```yaml
generators:
- list:
    elements:
    - app: backend
      path: k8s_helm/backend
      namespace: meo-stationery
    - app: database
      path: k8s_helm/database
      namespace: database
    - app: new-service          # ADD THIS
      path: k8s_helm/new-service
      namespace: meo-stationery
```

Git commit + push → ArgoCD auto-generates Applications for all envs!

## Adding New Environment

Edit `argocd/appsets/appset-applications.yaml`:

```yaml
- list:
    elements:
    - env: dev
      project: dev
      server: https://10.1.101.198:6443
      branch: dev
    - env: staging              # ADD THIS
      project: staging
      server: https://10.3.101.10:6443
      branch: main
    - env: prod
      project: prod
      server: https://10.2.101.11:6443
      branch: main
```

Git commit + push → All apps auto-deployed to new environment!

## Notifications Setup

See `argocd/notifications/README.md` for Slack integration.

## Troubleshooting

### ApplicationSets not creating Applications

```bash
kubectl describe applicationset applications -n argocd
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-applicationset-controller
```

### Applications stuck OutOfSync

```bash
argocd app get <app-name> --grpc-web
argocd app sync <app-name> --grpc-web
```

### Root app not syncing

```bash
kubectl describe application root-appsets -n argocd
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

## Migration from Old Structure

If migrating from Helm+Kustomize overlays:

1. ✅ Apply ApplicationSets (parallel with old structure)
2. ✅ Verify new Applications match old specs
3. ⚠️ Delete old Applications: `kubectl delete -f argocd/applications/overlays/`
4. ✅ Keep ApplicationSets - apps recreate instantly
5. ✅ Update documentation

## Rollback

```bash
# Delete ApplicationSets
kubectl delete applicationset applications infrastructure -n argocd

# Restore old structure
./scripts/setup-argocd-management-apps.sh
```
