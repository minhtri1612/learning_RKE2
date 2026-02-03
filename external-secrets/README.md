# External Secrets (AWS Secrets Manager → Kubernetes)

Terraform đã tạo secret `meo-stationery/<env>/app-credentials` trong AWS Secrets Manager (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DATABASE_URL, NEXTAUTH_SECRET). External Secrets Operator (ESO) đồng bộ sang K8s Secret để backend và database chart dùng.

## 1. Cài External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
```

## 2. AWS credentials cho ESO (tự động)

**Terraform** đã tạo IAM user `k8s-eso-secrets-<env>` với policy `secretsmanager:GetSecretValue` trên `meo-stationery/*`. **deploy.py** tự lấy access key từ Terraform output và tạo K8s Secret `aws-secrets-credentials` khi chưa có. Không cần tạo tay.

Sau **terraform destroy + apply**: IAM user mới → access key mới. Xóa Secret cũ rồi chạy lại deploy để tạo Secret mới:
```bash
kubectl delete secret aws-secrets-credentials -n external-secrets
./deploy.py dev
```

## 3. Áp dụng SecretStore + ExternalSecret theo env

Sửa `environments/<env>/*.yaml` cho đúng AWS region và tên secret. Rồi:

```bash
kubectl apply -f external-secrets/secretstore.yaml
kubectl apply -f external-secrets/environments/dev/
```

Sau khi ESO tạo xong K8s Secret, deploy ArgoCD apps (backend + database) với values có `existingSecret.name` đã set.

## 4. Troubleshooting: postgres pod "secret postgres not found"

Secret `postgres` do ESO tạo khi sync ExternalSecret. Nếu không có:

1. **Tạo AWS credentials cho ESO** (một lần):
   ```bash
   kubectl create secret generic aws-secrets-credentials -n external-secrets \
     --from-literal=access-key="YOUR_AWS_ACCESS_KEY" \
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
