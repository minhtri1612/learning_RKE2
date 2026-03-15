# Layer 1 – Developer

**Dev chỉ sửa trong folder này.**

## File theo môi trường

| File       | Môi trường |
|-----------|------------|
| `dev.yaml` | Dev       |
| `prod.yaml` | Prod      |

## Version & rollback

- **version** (trong từng `services.<tên>.version`) = bản đang chạy (branch/tag).
- **Rollback:** Sửa `version` về bản cũ (vd `v1.2.4`), commit + push. Argo CD sẽ sync.

## Các field thường sửa

- `services.backend.version` – bản backend (rollback đổi ở đây).
- `services.backend.replicaCount` – số replica.
- `services.backend.ingress.host` – domain.
- `services.database.version` – bản database.
- `services.database.replicas`, `services.database.persistence.size` – tùy env.

**Không sửa:** `argocd/`, `k8s_helm/`.
