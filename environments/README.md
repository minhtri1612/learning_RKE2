# Layer 1 – Developer

**Dev chỉ sửa trong folder này.**

## File theo môi trường

| File       | Môi trường |
|-----------|------------|
| `dev.yaml` | Dev       |
| `prod.yaml` | Prod      |

## Developer chỉ cần quan tâm: version

- **version** (trong `services.backend.version` và `services.database.version`) = bản đang chạy (tag/branch).
- **Deploy / rollback:** Sửa `version` thành tag cần chạy, commit + push. Argo CD sẽ sync.
- Các config khác (replicaCount, host, secret, resources, …) do DevOps quản lý trong `argocd/stacks/app-base.yaml`.

**Không sửa:** `argocd/`, `k8s_helm/`.
