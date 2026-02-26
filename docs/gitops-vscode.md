# 🚀 GitOps Flow - ArgoCD Pipeline

> **GitOps = Git là Single Source of Truth**
> 
> Mọi thay đổi infrastructure/application đều qua Git → ArgoCD tự động sync lên Kubernetes

---

## 📊 Architecture Overview

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│          │      │          │      │          │      │          │
│Developer │─────▶│  GitHub  │─────▶│  ArgoCD  │─────▶│   K8s    │
│          │ push │          │ poll │(Mgmt)    │apply │(Dev/Prod)│
│          │      │          │      │          │      │          │
└──────────┘      └──────────┘      └──────────┘      └──────────┘
```

---

## 🔄 Flow khi `git push`

### Step 1️⃣ Developer Push Code

```bash
git add -A
git commit -m "feat: update backend image to v2.0"
git push origin main
```

### Step 2️⃣ ArgoCD Detect Changes

```
┌─────────────────────────────────────────┐
│ ArgoCD polls GitHub every 3 minutes     │
│                                         │
│ Compares:                               │
│   📁 Git (Desired State)                │
│   ⚡ Cluster (Actual State)             │
│                                         │
│ Result: OutOfSync detected!             │
└─────────────────────────────────────────┘
```

### Step 3️⃣ Sync Waves Execute

```
Wave 0 ─────────────────────────────────────────────────────────
│
├── argocd-projects      (AppProjects: dev, prod, infrastructure)
├── argocd-clusters      (Cluster secrets: dev, prod)
├── argocd-repositories  (Git repo credentials)
└── argocd-config        (ArgoCD settings)
│
▼
Wave 1 ─────────────────────────────────────────────────────────
│
├── root-appsets         → Generates Applications:
│   │
│   ├── appset-applications.yaml (Matrix Generator)
│   │   │
│   │   │  definitions/     ×    config/
│   │   │  ┌──────────┐         ┌────────┐
│   │   │  │backend   │    ×    │dev     │  →  meo-station-backend-dev
│   │   │  │database  │    ×    │prod    │  →  meo-station-backend-prod
│   │   │  └──────────┘         └────────┘     meo-station-database-dev
│   │   │                                      meo-station-database-prod
│   │   │
│   └── appset-infrastructure.yaml
│       │
│       └── dev-ingress-nginx, prod-ingress-nginx
│
├── argocd-notifications
└── argocd-image-updater
│
▼
App Sync Waves ─────────────────────────────────────────────────
│
├── syncWave: "1"  →  database-dev, database-prod (deploy first)
│
└── syncWave: "5"  →  backend-dev, backend-prod (deploy after DB ready)
```

### Step 4️⃣ Kubernetes Apply

```
For each Application:

1. Helm Template
   ├── values.yaml (base)
   └── values-{env}.yaml (override)
   
2. kubectl apply -f <rendered-manifests>

3. Health Check
   ├── Deployment: all replicas ready?
   ├── Service: endpoints available?
   └── Pod: Running + Ready?

4. Status Update
   ├── ✅ Synced + Healthy
   └── ❌ OutOfSync / Degraded
```

---

## 📁 Repository Structure

```
learning_RKE2/
│
├── 📂 argocd/
│   │
│   ├── 📂 bootstrap/                 # 🚀 Entry Point
│   │   ├── 00-namespace.yaml
│   │   ├── 01-argocd-install.yaml
│   │   └── 02-root-app.yaml          # ← Apply 1 lần, quản lý tất cả
│   │
│   ├── 📂 projects/                  # Wave 0
│   │   ├── project-dev.yaml
│   │   ├── project-prod.yaml
│   │   └── project-infrastructure.yaml
│   │
│   ├── 📂 clusters/                  # Wave 0
│   │   ├── cluster-dev.yaml
│   │   └── cluster-prod.yaml
│   │
│   ├── 📂 appsets/                   # Wave 1
│   │   ├── appset-applications.yaml  # Matrix: app × env
│   │   ├── appset-infrastructure.yaml
│   │   └── argocd-image-updater-controller.yaml
│   │
│   └── 📂 apps/
│       ├── 📂 config/                # Environment configs
│       │   ├── dev.yaml              # env, project, clusterName
│       │   └── prod.yaml
│       │
│       └── 📂 definitions/           # Generic app definitions
│           ├── backend.yaml          # name, path, namespace, syncWave
│           └── database.yaml
│
└── 📂 k8s_helm/                      # Helm Charts
    ├── 📂 backend/
    │   ├── values.yaml               # Base
    │   ├── values-dev.yaml           # Dev override
    │   └── values-prod.yaml          # Prod override
    │
    └── 📂 database/
        ├── values.yaml
        ├── values-dev.yaml
        └── values-prod.yaml
```

---

## 🎯 Matrix Generator Explained

```yaml
# appset-applications.yaml

generators:
- matrix:
    generators:
    - git:
        files:
        - path: "argocd/apps/config/*.yaml"      # dev.yaml, prod.yaml
    - git:
        files:
        - path: "argocd/apps/definitions/*.yaml" # backend.yaml, database.yaml

# Result: 2 configs × 2 definitions = 4 Applications
```

| Definition | Config | Generated Application |
|------------|--------|----------------------|
| backend | dev | `meo-station-backend-dev` |
| backend | prod | `meo-station-backend-prod` |
| database | dev | `meo-station-database-dev` |
| database | prod | `meo-station-database-prod` |

**Lợi ích:**
- Thêm app mới → thêm 1 file vào `definitions/`
- Thêm env mới → thêm 1 file vào `config/`
- Không cần duplicate manifests!

---

## ⚡ Sync Policies

### Automated (Current)

```yaml
syncPolicy:
  automated:
    prune: true      # Xóa resources không còn trong Git
    selfHeal: true   # Auto-revert nếu ai kubectl edit
  syncOptions:
  - CreateNamespace=true
```

### Manual (Production Recommended)

```yaml
syncPolicy:
  automated: {}      # Chỉ detect, không auto-apply
  # Require manual sync button click
```

---

## 🔔 Notification Flow

```
Sync Event
    │
    ▼
┌─────────────────────────────────┐
│ argocd-notifications-controller │
│                                 │
│ Triggers:                       │
│ • on-deployed                   │
│ • on-sync-failed                │
│ • on-health-degraded            │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ 📱 Slack: #new-channel          │
│                                 │
│ ✅ backend-dev deployed         │
│ Revision: abc1234               │
└─────────────────────────────────┘
```

---

## 🔄 Rollback Options

### Option 1: Git Revert

```bash
git revert HEAD
git push origin main
# ArgoCD auto-syncs to previous state
```

### Option 2: ArgoCD CLI

```bash
# List revisions
argocd app history meo-station-backend-dev

# Rollback to specific revision
argocd app rollback meo-station-backend-dev 5

# Sync to specific commit
argocd app sync meo-station-backend-dev --revision abc1234
```

### Option 3: ArgoCD UI

```
Application → History → Select revision → Rollback
```

---

## 📋 Golden Rules

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ✅ DO:                                                     │
│     • Mọi thay đổi qua Git (PR → merge → push)             │
│     • Review changes trước khi merge                        │
│     • Tag releases cho production                           │
│                                                             │
│  ❌ DON'T:                                                  │
│     • kubectl apply -f trực tiếp                           │
│     • kubectl edit deployment                               │
│     • kubectl delete pod (để scale)                         │
│                                                             │
│  ArgoCD selfHeal sẽ REVERT mọi thay đổi ngoài Git!         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Debugging Commands

```bash
# Check app status
argocd app get meo-station-backend-dev

# View sync diff
argocd app diff meo-station-backend-dev

# Force refresh from Git
argocd app get meo-station-backend-dev --refresh

# View app logs
argocd app logs meo-station-backend-dev

# Sync with prune
argocd app sync meo-station-backend-dev --prune
```

---

## 📈 Summary

```
Developer ──push──▶ GitHub ──poll──▶ ArgoCD ──apply──▶ Kubernetes
                       │                │
                       │                ▼
                       │         ┌─────────────┐
                       │         │ Wave 0      │ projects, clusters
                       │         │ Wave 1      │ appsets, tools
                       │         │ syncWave 1  │ database
                       │         │ syncWave 5  │ backend
                       │         └─────────────┘
                       │                │
                       └────────────────┼─────── Single Source of Truth
                                        ▼
                                   ✅ Synced
                                   ✅ Healthy
```
