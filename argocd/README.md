# Argo CD Applications (dev / staging / prod)

Cấu trúc theo môi trường:

- `environments/dev/` – backend + database cho **dev** (meo-station-backend-dev, meo-station-database-dev)
- `environments/staging/` – cho **staging**
- `environments/prod/` – cho **prod**

## Apply từ repo (local hoặc trên master)

Từ thư mục gốc repo (có `argocd/environments/`):

```bash
./scripts/apply-argocd-apps.sh dev      # dev
./scripts/apply-argocd-apps.sh staging   # staging
./scripts/apply-argocd-apps.sh prod      # prod
```

`deploy.py` cũng apply từ đây: `argocd/environments/$TERRAFORM_ENV/` (khi chạy từ máy local có KUBECONFIG trỏ cluster).

## Repo GitOps (learning_RKE2)

Argo CD sync **source** (Helm charts) từ repo GitOps. Application manifests (file trong `argocd/environments/`) cần được **apply bằng kubectl** (từ deploy.py hoặc script trên).

**Nếu repo GitOps (learning_RKE2) chưa có thư mục `argocd/environments/`:** copy/push cả thư mục `argocd/environments/` từ repo này (practice_RKE2) sang learning_RKE2 rồi push. Sau đó trên master: `git clone learning_RKE2 && cd learning_RKE2 && ./scripts/apply-argocd-apps.sh dev`.
