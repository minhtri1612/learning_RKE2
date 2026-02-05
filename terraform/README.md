# Terraform – RKE2 + OpenVPN + ALB/NLB

## Cấu trúc

- **`modules/`** – VPC, IAM, keys, certificate, **secrets** (AWS Secrets Manager + random RKE2 token), loadbalancers, openvpn, rke2
- **`environments/dev`** – Dev (terraform.tfvars có sẵn)
- **`environments/prod`** – Prod (copy `terraform.tfvars.example` → `terraform.tfvars`, điền `my_ip`, `rke2_token`)
- **`environments/management`** – Management (chỉ ArgoCD)

## Chạy theo environment

```bash
# Dev
terraform -chdir=environments/dev init -input=false
terraform -chdir=environments/dev apply -var-file=terraform.tfvars -auto-approve -input=false

# Prod (sau khi copy terraform.tfvars.example → terraform.tfvars và điền my_ip, rke2_token)
terraform -chdir=environments/prod init -input=false
terraform -chdir=environments/prod apply -var-file=terraform.tfvars -auto-approve -input=false
```

Outputs (OpenVPN IP, NLB/ALB DNS, SSH key path) lấy bằng:

```bash
terraform -chdir=environments/dev output -json
```

**deploy.py:** Dùng `environments/dev` mặc định; SSH key: `terraform/environments/dev/k8s-key.pem`. Chạy env khác: `TF_ENV=prod python deploy.py` hoặc `./deploy.py management`.

**State:** State và file `.terraform/` nằm trong từng `environments/<env>/`. Nếu trước đây có state ở root (terraform.tfstate), hạ tầng cũ do root quản lý; giờ apply từ `environments/dev` sẽ tạo state mới trong `environments/dev/`. Có thể import/migrate resource từ state cũ nếu cần, hoặc destroy root stack rồi apply env (tạo lại hạ tầng).
