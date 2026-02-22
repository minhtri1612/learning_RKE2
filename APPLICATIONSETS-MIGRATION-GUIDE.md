# ApplicationSets Migration Guide

Migration từ Helm+Kustomize overlays sang ApplicationSets pattern cho enterprise production.

---

## Why ApplicationSets?

### Current Problem (Helm + Kustomize)

```
2 apps × 2 envs = 4 Application definitions
15 apps × 3 envs = 45 Application definitions (enterprise)

→ Phải maintain 45 YAMLs riêng biệt!
→ Copy-paste errors
→ Không consistent
```

### Solution (ApplicationSets)

```
1 ApplicationSet × matrix(apps, envs) = Auto-generate all Applications

→ Maintain 1 ApplicationSet
→ No duplication
→ Guaranteed consistency
```

---

## What Changed

### Before (Old Structure)

```
argocd/applications/
  ├── base/
  │   ├── Chart.yaml
  │   ├── templates/application.yaml
  │   └── values.yaml
  └── overlays/
      ├── dev/values.yaml
      └── prod/values.yaml

Deploy: ./scripts/setup-argocd-management-apps.sh
```

**Manual:** Edit overlays → Run script → Applications updated

### After (ApplicationSets)

```
argocd/appsets/
  ├── appset-applications.yaml     # Matrix: apps × envs
  └── appset-infrastructure.yaml

Deploy: kubectl apply -f argocd/bootstrap/root-app.yaml
```

**GitOps:** Edit ApplicationSet → Git push → Auto-sync → Applications updated

---

## Migration Steps

### Step 1: Apply ApplicationSets (Parallel Test)

```bash
# Ensure KUBECONFIG set
export KUBECONFIG=/home/minhtri/Downloads/practice_RKE2/.kube_config_rke2_management_tunnel.yaml

# Apply staging project
kubectl apply -f argocd/projects/project-staging.yaml

# Apply ApplicationSets (will create NEW Applications with same names)
kubectl apply -f argocd/appsets/appset-applications.yaml
```

**Result:** ApplicationSet creates Applications, but old Applications still exist.

### Step 2: Compare Old vs New Applications

```bash
# List all applications
kubectl get applications -n argocd

# Compare specs (should be identical)
kubectl get application meo-station-backend-dev -n argocd -o yaml > old-app.yaml

# Wait for ApplicationSet to generate
sleep 10

kubectl get application meo-station-backend-dev -n argocd -o yaml > new-app.yaml

diff old-app.yaml new-app.yaml
# Should show minimal differences (owner references, timestamps)
```

### Step 3: Monitor Health

```bash
# Watch Applications
kubectl get applications -n argocd -w

# All should be Healthy + Synced
```

### Step 4: Cutover (Delete Old, Keep ApplicationSets)

```bash
# Delete Applications managed by old Helm chart
# (ApplicationSet will recreate them immediately)

# Delete old Applications
kubectl delete application meo-station-backend-dev -n argocd
kubectl delete application meo-station-backend-prod -n argocd
kubectl delete application meo-station-database-dev -n argocd
kubectl delete application meo-station-database-prod -n argocd

# Wait 5 seconds - ApplicationSet will recreate them
sleep 5

kubectl get applications -n argocd
# Applications should be back, managed by ApplicationSet
```

### Step 5: Verify ApplicationSet Ownership

```bash
kubectl get application meo-station-backend-dev -n argocd -o yaml | grep -A 2 ownerReferences

# Should show:
# ownerReferences:
# - apiVersion: argoproj.io/v1alpha1
#   kind: ApplicationSet
#   name: applications
```

### Step 6: Apply Root App (GitOps)

```bash
kubectl apply -f argocd/bootstrap/root-app.yaml
```

This creates:
- `root-appsets` - Syncs ApplicationSets from Git
- `argocd-notifications` - Syncs notification config

**Now:** Any change to appsets/ in Git → ArgoCD auto-sync → Applications updated!

---

## Testing ApplicationSets

### Test 1: Add Test Application

Edit `argocd/appsets/appset-applications.yaml`, add:

```yaml
- app: test-app
  path: k8s_helm/test
  namespace: test
```

```bash
git add argocd/appsets/appset-applications.yaml
git commit -m "Test: Add test-app to ApplicationSet"
git push origin main

# Wait 3 minutes (ArgoCD sync interval)
kubectl get applications -n argocd | grep test-app

# Should see:
# meo-station-test-app-dev
# meo-station-test-app-prod
```

### Test 2: Remove Test Application

Edit `argocd/appsets/appset-applications.yaml`, remove test-app:

```bash
git commit -m "Test: Remove test-app"
git push origin main

# Wait 3 minutes
kubectl get applications -n argocd | grep test-app

# Applications should be pruned (deleted)
```

### Test 3: Update Environment Server URL

Edit ApplicationSet, change dev server URL:

```bash
git commit -m "Update dev cluster URL"
git push origin main

# All dev Applications will update to new server
```

---

## Rollback Plan

If ApplicationSets cause issues:

### Quick Rollback

```bash
# 1. Delete ApplicationSets
kubectl delete applicationset applications infrastructure -n argocd

# 2. Restore old Applications via script
cd /home/minhtri/Downloads/practice_RKE2
./scripts/setup-argocd-management-apps.sh

# 3. Delete root app
kubectl delete application root-appsets argocd-notifications -n argocd
```

### Verify Rollback

```bash
kubectl get applications -n argocd
# Should show old Applications working normally
```

---

## Post-Migration Benefits

### Developer Experience

**Add new microservice:**

**Before:**
1. Edit `applications/overlays/dev/values.yaml`
2. Edit `applications/overlays/staging/values.yaml`
3. Edit `applications/overlays/prod/values.yaml`
4. Run script or wait for sync

**After:**
1. Add 3 lines to ApplicationSet
2. Git push
3. Done - deployed to all envs!

### Operations Team

**Scale to 50 microservices:**

**Before:** Maintain 150 Application YAMLs (50 × 3 envs)

**After:** Maintain 1 ApplicationSet with 50-line list

### Consistency

**Before:** Dev/staging/prod configs might drift (copy-paste errors)

**After:** Guaranteed identical except for environment-specific values

---

## Advanced: Multi-Cluster ApplicationSet Generator

For future use with cluster generator:

```yaml
spec:
  generators:
  - matrix:
      generators:
      - git:
          repoURL: https://github.com/minhtri1612/learning_RKE2.git
          directories:
          - path: k8s_helm/*
      - cluster:
          selector:
            matchLabels:
              env: dev
```

This auto-discovers apps from Git directories and deploys to clusters matching labels.

---

## Monitoring

### Check ApplicationSet Health

```bash
kubectl get applicationset -n argocd
kubectl describe applicationset applications -n argocd
```

### Check Generated Applications

```bash
kubectl get applications -n argocd -l app.kubernetes.io/instance=applications

# Filter by environment
kubectl get applications -n argocd -o json | \
  jq '.items[] | select(.metadata.name | contains("dev")) | .metadata.name'
```

### ApplicationSet Controller Logs

```bash
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-applicationset-controller -f
```

---

## Notifications Setup

See `notifications/README.md` for Slack integration.

**Quick setup:**

```bash
# Create Slack token secret
kubectl create secret generic argocd-notifications-secret \
  -n argocd \
  --from-literal=slack-token=xoxb-YOUR-TOKEN

# Apply notifications config
kubectl apply -f argocd/notifications/argocd-notifications-cm.yaml

# Subscribe apps to notifications
kubectl patch application meo-station-backend-prod -n argocd \
  --type merge \
  -p '{"metadata":{"annotations":{"notifications.argoproj.io/subscribe.on-deployed.slack":"prod-deployments"}}}'
```

---

## Summary

✅ **Completed:**
- ApplicationSets created for applications + infrastructure
- Notifications configured (Slack)
- Staging project added
- Bootstrap updated for ApplicationSets pattern
- Documentation updated

⏸️ **Manual Steps Required:**
1. Test ApplicationSets in parallel
2. Verify Applications match
3. Cutover (delete old Applications)
4. Setup Slack notifications (optional)

🚀 **Ready for production with 15+ microservices!**
