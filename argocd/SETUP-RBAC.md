# Setup RBAC cho ArgoCD

Hướng dẫn kích hoạt phân quyền dev/prod trong ArgoCD.

---

## Hiện trạng (sau khi update)

✅ **Applications đã dùng Projects:**
- Dev apps → `project: dev`
- Prod apps → `project: prod`

✅ **RBAC policies đã define** trong `rbac/argocd-rbac-cm.yaml`:
- **Dev role:** Chỉ sync dev, KHÔNG được prod
- **Prod role:** Sync cả dev + prod (quyền cao hơn)
- **Admin role:** Tất cả

⏸️ **Chưa apply** → hiện tại vẫn chưa có phân quyền

---

## Kích hoạt RBAC

### Bước 1: Apply Projects

```bash
kubectl apply -f argocd/projects/
```

Kiểm tra:
```bash
kubectl get appproject -n argocd
# Sẽ thấy: dev, prod, infrastructure
```

---

### Bước 2: Apply RBAC

```bash
kubectl apply -f argocd/rbac/
```

ArgoCD sẽ tự reload config (không cần restart).

Kiểm tra:
```bash
kubectl get configmap argocd-rbac-cm -n argocd -o yaml
```

---

### Bước 3: Assign users vào roles

#### Option A: Local users (không SSO)

Tạo local user trong ArgoCD:
```bash
# Lấy admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Login ArgoCD CLI
argocd login argocd.local --username admin --password <password>

# Tạo user dev
argocd account update-password --account dev-user --new-password <dev-password>
```

Sửa `rbac/argocd-rbac-cm.yaml`:
```yaml
policy.csv: |
  # ...existing policies...
  
  # Map local users
  g, dev-user, role:dev
  g, prod-user, role:prod
```

Apply lại:
```bash
kubectl apply -f argocd/rbac/argocd-rbac-cm.yaml
```

---

#### Option B: SSO (Google, GitHub, etc.)

Sửa `rbac/argocd-cm.yaml`:
```yaml
data:
  dex.config: |
    connectors:
    - type: google
      id: google
      name: Google
      config:
        issuer: https://accounts.google.com
        clientID: $GOOGLE_CLIENT_ID
        clientSecret: $GOOGLE_CLIENT_SECRET
        redirectURI: https://argocd.local/api/dex/callback
```

Sửa `rbac/argocd-rbac-cm.yaml`:
```yaml
policy.csv: |
  # Map SSO users
  g, dev@company.com, role:dev
  g, prod@company.com, role:prod
  g, admin@company.com, role:admin
```

Apply:
```bash
kubectl apply -f argocd/rbac/
```

---

### Bước 4: Deploy lại Applications với Projects

```bash
# Nếu dùng script
./scripts/setup-argocd-management-apps.sh

# Hoặc dùng root-app GitOps (sau khi hardcode URLs)
kubectl apply -f argocd/bootstrap/root-app.yaml
```

---

## Test RBAC

### Test với dev user

```bash
# Login as dev
argocd login argocd.local --username dev-user

# Được phép: sync dev apps
argocd app sync meo-station-backend-dev
argocd app sync meo-station-database-dev

# BỊ TỪ CHỐI: sync prod apps
argocd app sync meo-station-backend-prod
# Error: permission denied
```

---

### Test với prod user

```bash
# Login as prod
argocd login argocd.local --username prod-user

# Được phép: sync cả dev và prod
argocd app sync meo-station-backend-dev
argocd app sync meo-station-backend-prod
argocd app sync meo-station-database-prod
```

---

## Phân quyền hiện tại

| Role | Dev Apps | Prod Apps | Infrastructure |
|------|----------|-----------|----------------|
| **dev** | ✅ Sync | ❌ Chỉ xem | ❌ Chỉ xem |
| **prod** | ✅ Sync | ✅ Sync | ❌ Chỉ xem |
| **admin** | ✅ Full | ✅ Full | ✅ Full |

---

## Tắt RBAC (quay lại default)

Xóa RBAC ConfigMap:
```bash
kubectl delete configmap argocd-rbac-cm -n argocd
```

ArgoCD sẽ quay lại default: ai cũng có quyền admin.

---

## Troubleshooting

### User bị "permission denied"

1. Kiểm tra role mapping:
   ```bash
   kubectl get configmap argocd-rbac-cm -n argocd -o yaml
   ```

2. Kiểm tra Application thuộc project nào:
   ```bash
   argocd app get meo-station-backend-dev -o yaml | grep project
   ```

3. Test policy:
   ```bash
   argocd admin settings rbac can dev-user sync applications 'dev/*'
   # Should return: yes
   ```

### RBAC không apply

ArgoCD cache config. Restart:
```bash
kubectl rollout restart deployment argocd-server -n argocd
```

---

## Tóm lại

1. ✅ Applications đã dùng Projects (dev, prod)
2. Apply Projects: `kubectl apply -f argocd/projects/`
3. Apply RBAC: `kubectl apply -f argocd/rbac/`
4. Assign users vào roles (local hoặc SSO)
5. Test quyền

Nếu không cần RBAC → **không cần làm gì**, giữ nguyên như hiện tại.
