# Flow deploy đầy đủ (provision + configure)

Thứ tự chạy script **không đổi**:

1. `./provision.py management` → AWS infra + OpenVPN  
2. Bật VPN: `sudo killall openvpn; sudo openvpn --config sep_tong-tcp.ovpn` (hoặc file .ovpn của bạn)  
3. `./configure.py management` → cài ArgoCD + bootstrap  
4. `./provision.py dev` → AWS infra dev  
5. `./configure.py dev` → Rancher + ESO (dev)  
6. `./provision.py prod` → AWS infra prod  
7. `./configure.py prod` → Rancher + ESO (prod)  

## Khi Terraform báo "No changes" nhưng ArgoCD vẫn 502

- **Terraform apply = No changes** nghĩa là state khớp config (instance có thể vẫn tồn tại, hoặc state chưa thấy instance đã mất).
- Nếu **instance management vẫn còn** (kiểm tra EC2 console): không cần provision lại. Chỉ cần **bật VPN** rồi chạy **bước 3**: `./configure.py management` để cài lại ArgoCD lên cluster (node có thể mới/trống).
- Nếu **instance management đã mất** (Spot terminate) mà Terraform vẫn không tạo lại: ép tạo lại bằng cách xóa resource khỏi state rồi apply:
  ```bash
  cd terraform/environments/management
  terraform state rm 'module.rke2.aws_instance.masters[0]'
  terraform state rm 'module.rke2.aws_instance.workers[0]'   # nếu có worker
  terraform apply -var-file=terraform.tfvars -auto-approve
  ```
  Sau khi instance mới lên, chạy lại **bước 2 (VPN)** rồi **bước 3** (`./configure.py management`).

## Sau khi destroy rồi apply lại – secret có còn sai không?

**Có.** Terraform khi apply lại sẽ:

- **Tạo mới** secret `meo-stationery/{env}/app-credentials` (hoặc `-v2`) với **password ngẫu nhiên** (random_password).
- **Không** quản lý secret `/meo-stationery/{env}/database` (secret đó không nằm trong Terraform).

Kết quả: **DATABASE_URL** (từ app-credentials) dùng password mới random, còn **Postgres** đọc từ `/meo-stationery/{env}/database` (vẫn password cũ) → **lệch password** → P1000 lại.

**Cần làm sau khi destroy + apply xong (trước khi migration chạy ổn):**

1. **Dev:** Chạy script đồng bộ password rồi (nếu cần) reset DB:
   ```bash
   export KUBECONFIG=/path/to/kube_config_rke2_dev.yaml
   ./scripts/sync-dev-db-and-backend-secrets.sh --cluster --reset-db
   ```
   (Script ghi cùng một password vào AWS: database + app-credentials-v2; `--reset-db` để Postgres init lại với password đó.)
2. **Prod:** Đặt cùng một password cho database và app-credentials trong AWS (put-secret-value), rồi xóa K8s secret database + backend để ESO tạo lại; nếu Postgres đã init với password cũ thì phải đổi password trong DB hoặc reset PVC tương tự dev.

**Spot bị thu hồi:** Destroy + apply không làm chuyện đó hết. Nếu vẫn dùng Spot (`use_spot_instances = true`), instance vẫn có thể bị AWS terminate lại. Giảm rủi ro: master dùng On-Demand, hoặc tăng worker_count.

## Cần thay đổi gì không?

**Script (`provision.py`, `configure.py`) không cần sửa.**

Chỉ cần: **push code mới lên repo mà ArgoCD đọc** (vd. `learning_RKE2`) **trước khi chạy bước 3** (hoặc trước khi ArgoCD sync lần đầu). Cụ thể:

- Repo phải có: `argocd/apps/definitions/*.yaml` (định nghĩa app generic: backend, database), `argocd/appsets/appset-applications.yaml` (ApplicationSet matrix: list env dev/prod × definitions). App (meo-station-backend-dev/prod, database-dev/prod) do ApplicationSet sinh, không còn folder argocd/apps/dev|prod với từng file.

Nếu chạy bước 3 khi repo chưa push code mới, ArgoCD sẽ sync theo state cũ. Sau khi push, Refresh/Sync lại root app (root-appsets) là được.
