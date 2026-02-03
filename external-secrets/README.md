# External Secrets (AWS Secrets Manager → Kubernetes)

Terraform đã tạo secret `meo-stationery/<env>/app-credentials` trong AWS Secrets Manager (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DATABASE_URL, NEXTAUTH_SECRET). External Secrets Operator (ESO) đồng bộ sang K8s Secret để backend và database chart dùng.

## 1. Cài External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
```

## 2. Tạo K8s Secret chứa AWS credentials (cho ESO đọc Secrets Manager)

Tạo IAM user (hoặc dùng role) có quyền `secretsmanager:GetSecretValue` với resource `meo-stationery/*`. Rồi:

```bash
kubectl create secret generic aws-secrets-credentials \
  -n external-secrets \
  --from-literal=access-key="YOUR_AWS_ACCESS_KEY" \
  --from-literal=secret-access-key="YOUR_AWS_SECRET_ACCESS_KEY"
```

(Prod nên dùng IRSA / OIDC thay vì static key.)

## 3. Áp dụng SecretStore + ExternalSecret theo env

Sửa `environments/<env>/*.yaml` cho đúng AWS region và tên secret. Rồi:

```bash
kubectl apply -f external-secrets/secretstore.yaml
kubectl apply -f external-secrets/environments/dev/
```

Sau khi ESO tạo xong K8s Secret, deploy ArgoCD apps (backend + database) với values có `existingSecret.name` đã set.
