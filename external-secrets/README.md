# External Secrets (AWS Secrets Manager → Kubernetes)

Terraform đã tạo secret `meo-stationery/<env>/app-credentials` trong AWS Secrets Manager (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DATABASE_URL, NEXTAUTH_SECRET). External Secrets Operator (ESO) đồng bộ sang K8s Secret để backend và database chart dùng.

## 1. Cài External Secrets Operator

**KinD 1.28 hoặc K8s chưa lên 1.31:** chart ESO từ **0.20.1** trở lên có CRD `selectableFields` không tương thích → ghim chart, ví dụ:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --version 0.19.2 \
  -n external-secrets --create-namespace
```

Trên cluster **≥ 1.31** có thể bỏ `--version` để lấy bản mới nhất.

## 2. AWS credentials cho ESO (tự động)

**Terraform** đã tạo IAM user `k8s-eso-secrets-<env>` với policy `secretsmanager:GetSecretValue` trên `meo-stationery/*`. **deploy.py** tự lấy access key từ Terraform output và tạo K8s Secret `aws-credentials` khi chưa có. Không cần tạo tay.

Sau **terraform destroy + apply**: IAM user mới → access key mới. Xóa Secret cũ rồi chạy lại deploy để tạo Secret mới:
```bash
kubectl delete secret aws-credentials -n external-secrets
./deploy.py dev
```

## 3. Áp dụng SecretStore + ExternalSecret theo env

**deploy.py** tự động apply qua Helm chart khi chạy `./deploy.py dev` hoặc `./deploy.py prod` (staging: apply thủ công hoặc mở rộng deploy script).

Apply thủ công:
```bash
helm template external-secrets external-secrets/applications \
  -f external-secrets/applications/values.yaml \
  -f external-secrets/applications/values-dev.yaml | kubectl apply -f -

helm template external-secrets external-secrets/applications \
  -f external-secrets/applications/values.yaml \
  -f external-secrets/applications/values-staging.yaml | kubectl apply -f -
```

Sau khi ESO tạo xong K8s Secret, deploy ArgoCD apps (backend + database) với values có `existingSecret.name` đã set.

## 4. Cấu trúc (giống argocd/applications)

```
external-secrets/
├── applications/
│   ├── Chart.yaml
│   ├── values.yaml          # defaults
│   ├── values-dev.yaml
│   ├── values-staging.yaml
│   ├── values-prod.yaml
│   └── templates/
│       ├── secretstore.yaml
│       ├── backend-external-secret.yaml
│       └── database-external-secret.yaml
└── README.md
```

## 5. Troubleshooting: postgres pod "secret ... not found"

Secret do ESO tạo khi sync ExternalSecret. Nếu không có:

1. **Tạo AWS credentials cho ESO** (một lần):
   ```bash
   kubectl create secret generic aws-credentials -n external-secrets \
     --from-literal=access-key-id="YOUR_AWS_ACCESS_KEY_ID" \
     --from-literal=secret-access-key="YOUR_AWS_SECRET_ACCESS_KEY"
   ```
   Hoặc chạy: `AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... ./deploy.py dev`

2. **Kiểm tra trạng thái sync** (trên master hoặc máy có KUBECONFIG):
   ```bash
   kubectl get externalsecret -n database
   kubectl describe externalsecret database-secrets-dev -n database
   kubectl get secret -n database
   ```
   Nếu ExternalSecret có status `SecretSyncedError` hoặc `SecretStoreNotFound`, xem Events/Status để sửa (sai tên secret AWS, thiếu quyền IAM, v.v.).

3. **Sau khi Secret `postgres` có**, postgres pod sẽ tự chạy (hoặc xóa pod để tạo lại: `kubectl delete pod postgres-0 -n database`).
