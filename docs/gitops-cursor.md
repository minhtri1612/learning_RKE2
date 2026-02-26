# GitOps Flow – Thứ tự khi `git push`

Luồng từ lúc push code lên Git đến khi workload được sync lên cluster (repo practice_RKE2).

---

## 1. Tổng quan

- **Git** = single source of truth: manifest ArgoCD, Helm values, K8s YAML đều trong repo.
- **ArgoCD** so sánh Git với cluster và sync để cluster khớp Git.
- **Root Application** (bootstrap) được **apply một lần bằng tay**; các app con do root và ApplicationSet tạo ra **tự sync** khi Git đổi.

---

## 2. Bootstrap (một lần)

Apply tay theo thứ tự:

| Bước | Lệnh / Việc làm | Mục đích |
|------|------------------|----------|
| 1 | `kubectl apply -f argocd/bootstrap/00-namespace.yaml` | Tạo namespace `argocd` |
| 2 | Cài ArgoCD (vd: `configure.py` dùng `01-argocd-install.yaml`) | Cài ArgoCD core |
| 3 | `kubectl apply -f argocd/projects/` | ArgoCD Projects (dev, prod, infrastructure) |
| 4 | `kubectl apply -f argocd/rbac/` (nếu có) | RBAC ArgoCD |
| 5 | `kubectl apply -f argocd/bootstrap/02-root-app.yaml` | Tạo **Root Application** (projects, config, appsets, …) |

Sau bước 5, mọi thay đổi tiếp theo chỉ cần **git push**.

---

## 3. Khi `git push` – thứ tự xử lý

### 3.1. Phát hiện thay đổi

- Push lên branch ArgoCD đang theo dõi (vd: `main`).
- ArgoCD nhận commit mới qua **webhook** (nếu cấu hình) hoặc **polling** (mặc định ~3 phút).
- Mỗi Application có `source` trùng repo/branch sẽ thấy revision mới và được đánh dấu sync nếu có thay đổi trong `path` tương ứng.

### 3.2. Sync theo Sync-Wave (root)

Root được định nghĩa trong `argocd/bootstrap/02-root-app.yaml`. Các Application trong file này đã có sẵn trên cluster (do bootstrap bước 5) và sync **theo sync-wave**.

**Wave 0** (trước):

| Application | Path Git | Nội dung |
|-------------|----------|----------|
| `argocd-projects` | `argocd/projects` | Projects (dev, prod, infrastructure) |
| `argocd-clusters` | `argocd/clusters` | Cluster registration (dev/prod) |
| `argocd-repositories` | `argocd/repositories` | Repo credentials, known_hosts |
| `argocd-config` | `argocd/config` | ConfigMap/params ArgoCD (vd: argocd-cmd-params-cm) |

**Wave 1** (sau):

| Application | Path Git | Nội dung |
|-------------|----------|----------|
| `root-appsets` | `argocd/appsets` | ApplicationSets (applications, infrastructure, image-updater-controller, …) |
| `argocd-notifications` | `argocd/notifications` | Notification (Slack, email, …) |
| `argocd-image-updater` | `argocd/image-updater` | ConfigMap/Secret image-updater |

Trong cùng wave có thể chạy song song; ArgoCD đảm bảo wave 0 xong rồi mới wave 1.

### 3.3. ApplicationSet sinh Application

- Sau khi `root-appsets` sync, manifest trong `argocd/appsets/` (gồm ApplicationSet) được áp dụng.
- **ApplicationSet controller** chạy matrix:
  - `argocd/apps/config/*.yaml` → từng env (dev, prod) → `env`, `project`, `clusterName`, `valueFileSuffix`, `targetRevision`, …
  - `argocd/apps/definitions/*.yaml` → từng app (backend, database, …) → `name`, `path`, `namespace`, `syncWave`, …
  - Matrix = config × definitions → một Application mỗi cặp (vd: `meo-station-backend-dev`, `meo-station-database-prod`, …).
- Application được tạo/cập nhật với tham số từ config (env) và definitions (app).

### 3.4. Sync app từng env

- Mỗi Application (vd: `meo-station-backend-dev`) có `sync-wave` từ definition (vd: backend = 5, database = 1).
- ArgoCD sync theo wave (1 → 5 → …).
- Mỗi app: clone repo tại `targetRevision` → vào `path` (vd: `k8s_helm/backend`) → Helm với `values.yaml` + `values-<valueFileSuffix>.yaml` → apply lên **cluster đích** (dev/prod) và **namespace** tương ứng.

Kết quả: workload trên cluster dev/prod khớp Git.

---

## 4. Sơ đồ thứ tự

```
git push (main)
       │
       ▼
ArgoCD phát hiện revision mới (webhook hoặc polling)
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  ROOT (02-root-app) – sync theo wave                      │
├──────────────────────────────────────────────────────────┤
│  Wave 0: argocd-projects, argocd-clusters,               │
│          argocd-repositories, argocd-config              │
│  Wave 1: root-appsets, argocd-notifications,              │
│          argocd-image-updater                             │
└──────────────────────────────────────────────────────────┘
       │
       ▼ (sau khi root-appsets sync)
ApplicationSet "applications": matrix config × definitions
       │
       ▼
Tạo/cập nhật Application: meo-station-<name>-<env>
       │
       ▼
Sync từng Application theo syncWave (1 → 5 → …)
  source: repo @ path (k8s_helm/backend, …)
  destination: cluster (dev/prod) + namespace
       │
       ▼
Helm install/upgrade → workload lên cluster đích
```

---

## 5. Sửa Git → App nào bị ảnh hưởng

| Sửa trong Git | App bị ảnh hưởng | Kết quả |
|---------------|------------------|---------|
| `argocd/projects/`, `argocd/config/`, `argocd/clusters/`, `argocd/repositories/` | argocd-projects, argocd-config, argocd-clusters, argocd-repositories | Wave 0 → cập nhật Projects, config, clusters, repos |
| `argocd/appsets/*.yaml` | root-appsets | Wave 1 → cập nhật ApplicationSet → tạo/xóa/sửa Application (meo-station-*-*) |
| `argocd/apps/config/*.yaml` hoặc `argocd/apps/definitions/*.yaml` | ApplicationSet đọc lại | Thêm/bớt env hoặc app → thêm/bớt Application |
| `k8s_helm/<app>/` (values, templates) | Application tương ứng (vd: meo-station-backend-dev) | Sync app → Helm upgrade trên cluster đích |
| `argocd/image-updater/*.yaml` | argocd-image-updater | Wave 1 → cập nhật config/secret image-updater |

---

## 6. Lưu ý

- **Root Application** (trong `02-root-app.yaml`) **không** do ArgoCD sync từ Git; tạo một lần bằng `kubectl apply`. Đổi root (thêm/bớt app, path, wave) thì sửa YAML trong repo rồi **apply lại**.
- **ApplicationSet** chỉ sinh Application; sync nội dung (Helm, manifest) do từng Application làm.
- Repo đang dùng `automated` + `prune` + `selfHeal` → sau push ArgoCD tự sync và sửa lệch (trừ ignoreDifferences).

Cập nhật doc khi thêm app/project hoặc đổi cấu trúc bootstrap.
