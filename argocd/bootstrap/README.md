# Bootstrap ArgoCD

## Files

- **argocd-install.yaml** - Helm values để cài ArgoCD
- **root-app.yaml** - Root Application (App of Apps) cho GitOps tự động

---

## Setup

### 1. Cài ArgoCD

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm install argocd argo/argo-cd \
  -f argocd/bootstrap/argocd-install.yaml \
  -n argocd --create-namespace
```

Đợi ArgoCD ready:
```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s
```

---

### 2. Option A: Script-based (Recommended - linh hoạt với placeholder)

Tiếp tục dùng script như hiện tại:
```bash
./scripts/setup-argocd-management-apps.sh
```

**Ưu điểm:**
- Linh hoạt: script tự lấy cluster URL từ Terraform
- Placeholder `__CLUSTER_SERVER_DEV__` được replace tự động

**Nhược điểm:**
- Phải chạy script mỗi lần thay đổi applications

---

### 2. Option B: GitOps với root-app (Tự động sync)

**Bước 1:** Hardcode cluster URLs trong overlays

Sửa `argocd/applications/overlays/dev/values.yaml`:
```yaml
apps:
  backend:
    destination:
      server: https://10.1.101.10:6443  # thay bằng dev cluster IP
```

Tương tự cho `overlays/prod/values.yaml`.

**Bước 2:** Apply root app
```bash
kubectl apply -f argocd/bootstrap/root-app.yaml
```

**Ưu điểm:**
- GitOps thuần: push Git → ArgoCD tự sync
- Không cần chạy script

**Nhược điểm:**
- Cluster URL phải hardcode trong Git
- Ít linh hoạt khi cluster thay đổi

---

## Chọn approach nào?

| Scenario | Recommendation |
|----------|----------------|
| Solo dev, cluster URL thay đổi thường xuyên | **Script-based** (Option A) |
| Team, cluster ổn định, muốn full GitOps | **GitOps** (Option B) |
| Testing, learning | **Script-based** (đơn giản hơn) |

---

## Migration từ approach cũ

Nếu đang dùng script với cấu trúc applications/ cũ:
1. Cấu trúc đã được migrate sang base + overlays
2. Script đã được update tự động
3. Chạy script như cũ: `./scripts/setup-argocd-management-apps.sh`

Nếu muốn thử GitOps:
1. Hardcode URLs trong overlays/
2. Apply root-app.yaml
3. Test sync
4. Nếu OK → commit, push Git → ArgoCD sẽ sync tự động
