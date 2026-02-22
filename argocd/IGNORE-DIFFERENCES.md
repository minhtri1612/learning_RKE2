# ignoreDifferences Configuration Guide

## ⚠️ Important Change

**`ignoreDifferences` đã bị XÓA khỏi ApplicationSet** để tránh Go template syntax errors.

**Lý do:**
- ApplicationSet chỉ nên chứa deployment metadata (server, namespace, path)
- `ignoreDifferences` là application-specific config → thuộc về app repo

---

## 📍 Nơi Config `ignoreDifferences`

### Option 1: ArgoCD Application Manifest (Recommended)

**Location:** `learning_RKE2` repo (application code repo)

**Path:** `k8s_helm/backend/argocd-application.yaml` (tạo file mới)

```yaml
# k8s_helm/backend/argocd-application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: meo-station-backend-dev
  namespace: argocd
spec:
  # ... other fields (managed by ApplicationSet)
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas
```

**Nhược điểm:** ApplicationSet sẽ override file này (vì name conflict)

---

### Option 2: ArgoCD CLI (Quick fix)

```bash
argocd app patch meo-station-backend-dev --type json -p '[{
  "op": "add",
  "path": "/spec/ignoreDifferences",
  "value": [{
    "group": "apps",
    "kind": "Deployment",
    "jsonPointers": ["/spec/replicas"]
  }]
}]'
```

**Nhược điểm:** Mất khi recreate Application

---

### Option 3: ArgoCD ConfigMap (Global)

**Location:** `practice_RKE2/argocd/rbac/argocd-cm.yaml`

**Add:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-cm
  namespace: argocd
data:
  resource.customizations.ignoreDifferences.apps_Deployment: |
    jsonPointers:
    - /spec/replicas
  resource.customizations.ignoreDifferences.apps_StatefulSet: |
    jsonPointers:
    - /spec/volumeClaimTemplates
    - /spec/serviceName
```

**Ưu điểm:** 
- ✅ Áp dụng cho TẤT CẢ Deployments/StatefulSets
- ✅ Không cần config per-app

**Nhược điểm:**
- ❌ Global (không per-app)

---

### Option 4: Helm Values (Best for this project)

**Location:** `learning_RKE2/k8s_helm/backend/values.yaml`

**Add ArgoCD annotations:**
```yaml
# values.yaml
deployment:
  annotations:
    argocd.argoproj.io/compare-options: IgnoreExtraneous
    argocd.argoproj.io/sync-options: Prune=false
```

**HOẶC** dùng global ignore trong `argocd-cm.yaml` như Option 3.

---

## ✅ **RECOMMENDED: Option 3 (Global ConfigMap)**

Vì project này có pattern cố định:
- **Backend/Frontend** → Deployment → ignore `/spec/replicas`
- **Database** → StatefulSet → ignore `/spec/volumeClaimTemplates`

**Bước thực hiện:**

1. **Update `argocd/rbac/argocd-cm.yaml`:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-cm
  namespace: argocd
data:
  # Ignore replicas cho tất cả Deployments (HPA/manual scale)
  resource.customizations.ignoreDifferences.apps_Deployment: |
    jsonPointers:
    - /spec/replicas
  
  # Ignore volume templates cho tất cả StatefulSets (dynamic PV)
  resource.customizations.ignoreDifferences.apps_StatefulSet: |
    jsonPointers:
    - /spec/volumeClaimTemplates
    - /spec/serviceName
  
  # Optional: Ignore annotations managed by external controllers
  resource.customizations.ignoreDifferences.all: |
    managedFieldsManagers:
    - kube-controller-manager
```

2. **Apply:**
```bash
kubectl apply -f argocd/rbac/argocd-cm.yaml
kubectl rollout restart deployment argocd-server -n argocd
```

3. **Verify:**
```bash
kubectl get cm argocd-cm -n argocd -o yaml
```

---

## 🔍 Why This Approach?

### Before (ApplicationSet with ignoreDifferences)
```yaml
# ❌ Go template syntax → YAML linter errors
{{- if .ignoreDifferences }}
ignoreDifferences:
{{- toYaml .ignoreDifferences | nindent 6 }}
{{- end }}
```

**Problems:**
- YAML linter shows errors (false positives)
- Complex Go template logic
- Hard to maintain

### After (Global ConfigMap)
```yaml
# ✅ Clean YAML, no template syntax
resource.customizations.ignoreDifferences.apps_Deployment: |
  jsonPointers:
  - /spec/replicas
```

**Benefits:**
- ✅ No YAML errors
- ✅ Applies to all apps automatically
- ✅ Easy to maintain
- ✅ Centralized configuration

---

## 📚 ArgoCD Docs

Official docs on ignore differences:
- https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/

---

## 🎯 Summary

**ApplicationSet (practice_RKE2):**
- ✅ Deployment metadata only (server, namespace, path, branch, prune)
- ❌ NO application-specific config (ignoreDifferences, syncWaves, health)

**ArgoCD ConfigMap (practice_RKE2):**
- ✅ Global ignoreDifferences for all Deployments/StatefulSets

**Application Code (learning_RKE2):**
- ✅ Helm charts, values, actual app config
- ✅ App-specific overrides (if needed)

---

## 🚀 Next Steps

1. Update `argocd/rbac/argocd-cm.yaml` (see Option 3)
2. Apply: `kubectl apply -f argocd/rbac/`
3. Restart ArgoCD: `kubectl rollout restart deploy/argocd-server -n argocd`
4. Deploy: `./deploy.py`
