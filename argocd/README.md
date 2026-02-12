# ArgoCD Configuration

Cấu trúc GitOps cho ArgoCD quản lý applications trên các cluster dev/prod.

## Cấu trúc

```
argocd/
├── bootstrap/                          # Bootstrap ArgoCD
│   ├── argocd-install.yaml            # Helm values cho ArgoCD install
│   └── root-app.yaml                  # Root App of Apps
│
├── projects/                           # ArgoCD Projects cho RBAC
│   ├── project-dev.yaml
│   ├── project-prod.yaml
│   └── project-infrastructure.yaml
│
├── rbac/                               # RBAC Configuration
│   ├── argocd-rbac-cm.yaml           # RBAC policies
│   └── argocd-cm.yaml                 # ArgoCD config (SSO, etc.)
│
├── applications/
│   ├── base/                          # Base Helm chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       └── application.yaml
│   │
│   └── overlays/                      # Environment-specific values
│       ├── dev/
│       │   ├── values.yaml
│       │   └── kustomization.yaml
│       └── prod/
│           ├── values.yaml
│           └── kustomization.yaml
│
```

## Setup

### 1. Cài ArgoCD (lần đầu)

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm install argocd argo/argo-cd \
  -f argocd/bootstrap/argocd-install.yaml \
  -n argocd --create-namespace
```

### 2. Apply Projects và RBAC

```bash
kubectl apply -f argocd/projects/
kubectl apply -f argocd/rbac/
```

### 3. Bootstrap Root App (GitOps)

```bash
kubectl apply -f argocd/bootstrap/root-app.yaml
```

ArgoCD sẽ tự sync applications từ Git.

---

## Cách dùng

### Option A: GitOps (Recommended)

1. Sửa file trong `applications/overlays/dev/` hoặc `overlays/prod/`
2. Git commit + push
3. ArgoCD tự sync trong vài phút

### Option B: Script (Legacy - cần cập nhật)

```bash
# Cần update script để dùng base + overlays
./scripts/setup-argocd-management-apps.sh
```

---

## Placeholder Issue

**Vấn đề:** `__CLUSTER_SERVER_DEV__` và `__CLUSTER_SERVER_PROD__` trong values.yaml.

**Giải pháp:**

1. **Hardcode cluster URLs** trong Git (không linh hoạt):
   ```yaml
   destination:
     server: https://10.1.101.10:6443  # dev cluster
   ```

2. **Dùng ArgoCD Helm parameters** (phức tạp):
   - Truyền cluster URL qua ArgoCD Application spec
   - Cần sửa root-app.yaml

3. **Giữ script** (hiện tại):
   - Tiếp tục dùng `setup-argocd-management-apps.sh`
   - Không dùng root-app.yaml auto-sync

---

## Migration từ cấu trúc cũ

Cấu trúc cũ (script-based):
- `applications/Chart.yaml`, `values-dev.yaml`, `values-prod.yaml`
- `setup-argocd-management-apps.sh` chạy helm template + sed + kubectl apply

Cấu trúc mới (GitOps):
- `applications/base/` + `overlays/`
- `root-app.yaml` auto-sync từ Git

**Chuyển đổi:**
1. Test với root-app trước (apply thử)
2. Nếu placeholder issue → giữ script, bỏ root-app
3. Nếu OK → dùng root-app, xóa/archive script

---

## Troubleshooting

### Placeholder không được replace

ArgoCD sync raw từ Git → không có bước sed.

**Fix:** Sửa `overlays/dev/values.yaml` hardcode cluster URL:
```yaml
apps:
  backend:
    destination:
      server: https://10.1.101.10:6443
```

### Root app không sync

Kiểm tra:
```bash
kubectl get application root-app -n argocd -o yaml
kubectl describe application root-app -n argocd
```

Check logs:
```bash
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

---

## RBAC

Projects đã tạo:
- **dev** – Dev team chỉ deploy vào dev cluster
- **prod** – Prod team chỉ deploy vào prod cluster
- **infrastructure** – Admin quản lý infrastructure (ArgoCD, ESO, etc.)

Cấu hình users/roles trong `rbac/argocd-rbac-cm.yaml`.
