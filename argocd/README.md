# ArgoCD GitOps Structure

## 📁 Folder Structure

```
argocd/
├── bootstrap/              # Bootstrap ArgoCD - apply thủ công 1 lần
│   ├── 00-namespace.yaml
│   ├── 01-argocd-install.yaml
│   └── 02-root-app.yaml
│
├── projects/               # AppProjects - phân quyền
│   ├── infrastructure.yaml
│   ├── dev.yaml
│   └── prod.yaml
│
├── environments/           # Stacks theo environment
│   ├── dev/
│   │   ├── infrastructure-stack.yaml   # ingress-nginx, metrics-server
│   │   └── meostation-stack.yaml       # umbrella chart meo-station
│   └── prod/
│       ├── infrastructure-stack.yaml
│       └── meostation-stack.yaml
│
├── versions/               # Centralized version management
│   └── README.md
│
└── cluster-config/         # ArgoCD cluster configs
    ├── repositories.yaml
    └── rbac.yaml
```

## 🎯 Design Principles

### 1. Category-based Organization
- **projects/**: AppProjects (RBAC, permissions)
- **environments/**: Stacks grouped by env (dev/prod)
- **versions/**: Version pinning strategy

### 2. Naming Convention: `<env>-<project>-stack`
- `dev-infrastructure-stack`
- `dev-meostation-stack`
- `prod-infrastructure-stack`
- `prod-meostation-stack`

### 3. Only 2 Levels of App-in-App
```
root-app (Level 1)
├── dev-infrastructure-stack (Level 2) → K8s resources
├── dev-meostation-stack (Level 2) → K8s resources
├── prod-infrastructure-stack (Level 2)
└── prod-meostation-stack (Level 2)
```

## 🔄 Version Strategy

### Dev Environment
- `targetRevision: kind` (branch) - latest changes
- Auto-sync enabled

### Prod Environment
- `targetRevision: v1.x.x` (tag) - pinned version
- Manual sync only

### Promotion Flow
```
dev (branch: kind) → test OK → tag v1.x.x → prod uses tag
```

### Rollback
```
prod: change targetRevision from v1.2.0 → v1.1.0
```

## 🚀 Setup

```bash
# 1. Install ArgoCD
kubectl apply -f argocd/bootstrap/00-namespace.yaml
kubectl apply -f argocd/bootstrap/01-argocd-install.yaml

# 2. Apply root app (auto-sync everything)
kubectl apply -f argocd/bootstrap/02-root-app.yaml
```
