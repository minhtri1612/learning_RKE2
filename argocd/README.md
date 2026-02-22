# ArgoCD Configuration

Enterprise-grade GitOps structure using ApplicationSets for managing applications across multiple environments.

## Architecture

**ApplicationSets Pattern:** One ApplicationSet auto-generates Applications for all environments.

```
ApplicationSet (applications)
    ├─> meo-station-backend-dev    (auto-generated)
    ├─> meo-station-backend-prod   (auto-generated)
    ├─> meo-station-database-dev   (auto-generated)
    └─> meo-station-database-prod  (auto-generated)
```

**Benefits:**
- Add 1 app → auto-deployed to all envs
- Add 1 env → all apps auto-deployed
- Consistent configuration across envs
- Self-service for developers

## Structure

```
argocd/
├── bootstrap/                          # Bootstrap ArgoCD
│   ├── argocd-install.yaml            # Helm values cho ArgoCD install
│   ├── root-app.yaml                  # Root App syncs ApplicationSets
│   └── README.md                      # Setup instructions
│
├── appsets/                            # ApplicationSets (NEW - Enterprise pattern)
│   ├── appset-applications.yaml       # Generate apps for all envs
│   └── appset-infrastructure.yaml     # Generate infrastructure apps
│
├── projects/                           # ArgoCD Projects cho RBAC
│   ├── project-dev.yaml
│   ├── project-staging.yaml           # NEW - for future use
│   ├── project-prod.yaml
│   └── project-infrastructure.yaml
│
├── notifications/                      # NEW - Slack notifications
│   ├── argocd-notifications-cm.yaml
│   └── README.md
│
├── rbac/                               # RBAC Configuration
│   ├── argocd-rbac-cm.yaml           # RBAC policies
│   └── argocd-cm.yaml                 # ArgoCD config (SSO, etc.)
│
├── applications/                       # OLD - Legacy Helm+Kustomize (kept for reference)
│   ├── base/
│   └── overlays/
│
└── secrets/                            # External Secrets templates (NEW)
    ├── cluster-secret-store.yaml
    ├── backend-external-secret.yaml
    └── database-external-secret.yaml
```

## Setup (ApplicationSets Pattern)

See detailed instructions in `bootstrap/README.md`

### Quick Start

```bash
# 1. Install ArgoCD
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd \
  -f argocd/bootstrap/argocd-install.yaml \
  -n argocd --create-namespace

# 2. Apply Projects + RBAC
kubectl apply -f argocd/projects/
kubectl apply -f argocd/rbac/

# 3. Bootstrap Root App (starts GitOps)
kubectl apply -f argocd/bootstrap/root-app.yaml

# 4. Verify ApplicationSets created
kubectl get applicationset -n argocd

# 5. Verify Applications auto-generated
kubectl get applications -n argocd
```

---

## Working with ApplicationSets

### Add New Service (Auto-deploy to all envs)

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

Git commit + push → ArgoCD creates:
- `meo-station-new-service-dev`
- `meo-station-new-service-prod`

### Add New Environment (Auto-deploy all apps)

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

Git commit + push → ArgoCD creates all apps for staging.

### Update Application Configuration

Edit app Helm values in `learning_RKE2` repo:

```bash
# Example: Update backend dev replicas
vim k8s_helm/backend/values-dev.yaml
git commit -m "Update dev replicas"
git push origin dev

# Wait 3-5 minutes → ArgoCD auto-sync
```

---

## Legacy Setup (Old Helm+Kustomize)

**Deprecated:** Use ApplicationSets instead

The `applications/base` and `applications/overlays` folders are kept for reference but should not be used for new deployments.

To use legacy setup:

```bash
./scripts/setup-argocd-management-apps.sh
```

---

## ApplicationSets vs Manual Applications

### ApplicationSets (Current - Recommended)

**Pros:**
- Auto-generate Applications for all environments
- Add app once → deployed everywhere
- Consistent across envs
- Scale to 100+ apps easily

**Example:** Add app to list → 3 Applications created (dev/staging/prod)

### Manual Applications (Legacy)

**Cons:**
- Must create/update each Application YAML manually
- Prone to copy-paste errors
- Hard to maintain at scale

**Location:** `applications/base` + `overlays/` (deprecated, kept for reference)

---

## Troubleshooting

### ApplicationSets not generating Applications

```bash
# Check ApplicationSet status
kubectl describe applicationset applications -n argocd

# Check controller logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-applicationset-controller -f
```

### Applications OutOfSync

```bash
# Force sync
argocd app sync meo-station-backend-dev --grpc-web

# Check sync status
argocd app get meo-station-backend-dev --grpc-web
```

### Root app failed to sync

```bash
kubectl describe application root-appsets -n argocd
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

### Notifications not working

See `notifications/README.md` for Slack setup.

```bash
# Check notifications controller
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-notifications-controller -f
```

---

## RBAC & Projects

Projects configured:
- **dev** – Dev team deploy to dev cluster only
- **staging** – Staging team deploy to staging cluster only (future)
- **prod** – Prod team deploy to prod cluster only
- **infrastructure** – Admin manage infrastructure apps

User roles in `rbac/argocd-rbac-cm.yaml`:
- **role:admin** - Full access
- **role:dev** - Dev apps only
- **role:prod** - Prod + dev apps

See `SETUP-RBAC.md` for detailed RBAC configuration.
