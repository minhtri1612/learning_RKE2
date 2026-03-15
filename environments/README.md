# Layer 1 – Developer

**Dev chỉ sửa trong folder này.**

## File theo môi trường

| File       | Môi trường |
|-----------|------------|
| `dev.yaml` | Dev       |
| `prod.yaml` | Prod      |

## Version = targetRevision + image tag (backend)

- **services.backend.version** = bản đang chạy:
  - **Git:** Argo CD dùng làm `targetRevision` (branch hoặc tag của repo manifest).
  - **Docker:** Dùng làm image tag `minhtri1612/rke2:<version>`. Cần build & push image đúng tag trước khi đổi version.
- **services.database.version** = targetRevision cho chart database (image Postgres theo app-base).
- Các config khác do DevOps trong `argocd/stacks/app-base.yaml`.

---

## Workflows

### Kịch bản 4: Rollback prod về version cũ

Prod đang v1.2.4, deploy lỗi → rollback về v1.2.3.

**Cách 1 – Argo CD History (nhanh, không cần PR)**

- **UI:** Vào Argo CD → chọn Application **prod-backend-stack** → tab **HISTORY AND ROLLBACK** → chọn dòng revision tương ứng v1.2.3 (xem cột "Revision" hoặc "Deployed At") → bấm **Rollback**. Argo CD sẽ deploy lại đúng manifest từ lần sync đó.
- **CLI (quản lý history bằng CLI):**
  ```bash
  # Login (nếu chưa)
  argocd login <argocd-server> --insecure --username admin

  # Xem lịch sử sync của prod-backend-stack (ID = revision để rollback)
  argocd app history prod-backend-stack

  # Rollback về revision trước đó (lấy ID từ cột đầu tiên của history)
  argocd app rollback prod-backend-stack <revision-id>
  ```
  Ví dụ output `history`:
  ```
  ID  DATE                           REVISION
  0   2024-03-19T16:00:00+07:00     v1.2.4   # đang chạy, lỗi
  1   2024-03-18T10:00:00+07:00     v1.2.3   # bản ổn định
  ```
  → Rollback về v1.2.3: `argocd app rollback prod-backend-stack 1`

**Cách 2 – Git (đồng bộ Git với cluster)**

- Sửa `prod.yaml`: `services.backend.version: v1.2.3` → PR → merge → Argo CD sync (manual hoặc auto). Prod deploy lại đúng manifest + image v1.2.3. Cách này giữ Git là source of truth.

**Lưu ý:** Rollback qua Argo CD History **không đổi file trong Git**. Nếu muốn Git và cluster cùng trỏ v1.2.3, sau khi rollback qua UI/CLI nên revert commit trong repo (đổi lại prod.yaml về v1.2.3 rồi push).

### Kịch bản 8: Promote dev lên prod (QA đã test)

1. DevOps: `git tag v1.2.3 && git push origin v1.2.3`
2. Build & push image: `minhtri1612/rke2:v1.2.3`
3. Sửa `prod.yaml`: `services.backend.version: v1.2.3`
4. Tạo PR → 1 người approve → merge
5. Argo CD sync prod → deploy đúng v1.2.3.

### Kịch bản 9: Prod an toàn khi dev merge nhầm vào main

- `prod.yaml` dùng **tag cố định** (vd `v1.2.5`). Argo CD prod chỉ sync theo targetRevision = tag đó.
- Dev merge code chưa test vào `main` → prod **không** tự động đổi, vì prod không trỏ `main`.
- Chỉ khi đổi `version` trong prod.yaml (qua PR + approve) thì prod mới sync version mới.

**Không sửa:** `argocd/`, `k8s_helm/`.
