# terraform_secret — chỉ AWS Secrets Manager (dev / staging / prod)

Root Terraform **tách hẳn** khỏi `terraform/` (RKE2, VPC, …). Một `apply` tạo **ba secret** JSON trên Secrets Manager:

`{project_name}/{env}/app-credentials{suffix}`

## Các key trong JSON (khớp ExternalSecret `property`)

| Key |
|-----|
| `POSTGRES_USER` |
| `POSTGRES_PASSWORD` |
| `POSTGRES_DB` |
| `DATABASE_URL` |
| `NEXTAUTH_SECRET` |

## Chạy

```bash
cd terraform_secret
cp terraform.tfvars.example terraform.tfvars   # chỉnh nếu cần
terraform init
terraform apply
terraform output app_credentials_secret_names
```

Sau đó chỉnh `external-secrets/applications/values-*.yaml` cho trùng tên secret AWS vừa output.

## IAM cho External Secrets Operator

Stack tạo **một IAM user** + policy `secretsmanager:GetSecretValue` trên ARN prefix `secret:{project_name}/*` và **một access key**.

Lấy key (sau `apply`):

```bash
terraform output -raw eso_access_key_id
terraform output -raw eso_secret_access_key
```

Tạo Secret trong cluster (namespace `external-secrets`), khớp `ClusterSecretStore` trong repo:

```bash
kubectl -n external-secrets create secret generic aws-credentials \
  --from-literal=access-key-id="$(terraform output -raw eso_access_key_id)" \
  --from-literal=secret-access-key="$(terraform output -raw eso_secret_access_key)"
```

**Lưu ý:** Nếu đã có user ESO từ `terraform/environments/dev|prod`, đây là user **riêng** (hậu tố mặc định `multi`, chỉnh `eso_iam_user_suffix` nếu cần).
