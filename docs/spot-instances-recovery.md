# Spot instances bị thu hồi – cách xử lý

Khi dùng EC2 Spot (`use_spot_instances = true`), AWS có thể terminate instance bất cứ lúc nào → node mất, cluster thiếu node, pod Pending hoặc NotReady.

## Bước 1: Kiểm tra cluster (kubeconfig trỏ đúng env)

```bash
export KUBECONFIG=/path/to/kube_config_rke2_dev.yaml   # hoặc _prod
kubectl get nodes
kubectl get pods -A | grep -v Running
```

- Node **NotReady** / **Unknown** = EC2 đã mất hoặc không phản hồi.
- Pod **Pending** (0/N nodes available) = thiếu node hoặc node đầy.

## Bước 2: Xóa node chết khỏi Kubernetes

Để control plane không chờ node cũ và pod có thể reschedule:

```bash
# Xem node nào NotReady/Unknown
kubectl get nodes

# Xóa từng node chết (thay <node-name> bằng tên thật, ví dụ ip-10-1-101-234)
kubectl delete node <node-name>
```

Làm với **từng** node bị NotReady/Unknown. **Không** xóa node đang Ready (trừ khi chắc là instance cũ đã terminate).

## Bước 3: Terraform tạo lại EC2 (thay thế instance đã mất)

Terraform đang quản lý **số lượng** instance (master_count, worker_count). Instance bị terminate → khi apply Terraform sẽ thấy resource “mất” và **tạo mới** để đủ count.

**Dev:**

```bash
cd terraform/environments/dev
terraform init
terraform plan -var-file=terraform.tfvars   # sẽ thấy create thay cho instance đã mất
terraform apply -var-file=terraform.tfvars -auto-approve
```

**Prod:** tương tự, dùng `environments/prod` và tfvars của prod.

- Instance mới (master/worker) sẽ chạy user_data: join RKE2 bằng token + master IP.
- Sau vài phút: `kubectl get nodes` sẽ thấy node mới Ready.
- Pod đang Pending sẽ tự schedule lên node mới (nếu còn đủ capacity).

## Bước 4: (Tùy chọn) Cập nhật NLB/ALB target group

Module đã gắn target group theo `module.rke2.master_ids` / `worker_ids`. Sau khi Terraform apply, instance mới có ID mới → target group attachment cũng được tạo lại trong Terraform. Chỉ cần **apply đủ** (đã gồm `aws_lb_target_group_attachment`). Nếu sau apply vẫn lỗi health check, kiểm tra security group / port 6443 (NLB) và port 80 (ALB).

## Tóm tắt nhanh

1. `kubectl get nodes` → xóa node NotReady/Unknown: `kubectl delete node <name>`.
2. `terraform -chdir=terraform/environments/<dev|prod> apply -var-file=...` để tạo lại instance thiếu.
3. Đợi node mới Ready, pod tự schedule lại.

## Giảm rủi ro Spot về sau

- Tăng `worker_count` (ví dụ 3–4) để mất 1–2 con vẫn còn đủ.
- Cân nhắc **master** dùng On-Demand (`use_spot_instances = false` cho master, hoặc tách module master/worker) để control plane ổn định.
- Dùng **capacity rebalancing** (nếu chuyển sang ASG + Spot) để AWS cảnh báo trước khi reclaim.
