# Plan chi tiết: RKE2 + K8s Docker Operator

Plan chuyển từ mô hình "RKE2 trên mỗi môi trường" sang "1 RKE2 (Management) + EC2 chỉ cài Docker (Dev/Prod)", tích hợp [K8s Docker Operator](https://github.com/minhtri1612/k8s-docker).

---

## Giai đoạn 0: Chuẩn bị & backup

### 0.1 Backup và branch
- Clone/pull repo `practice_RKE2`, đảm bảo working tree sạch.
- Tạo branch: `git checkout -b feature/docker-operator-migration`.
- (Tùy chọn) Backup Terraform state: `terraform -chdir=terraform/environments/management state pull > backup_mgmt_state.json` (tương tự dev/prod).

### 0.2 Đọc cấu trúc hiện tại
- Mở `terraform/environments/dev/main.tf` và `prod/main.tf`: xác định chỗ gọi `module "rke2"`, biến truyền vào, và các `aws_lb_target_group_attachment` (NLB/ALB).
- Mở `terraform/environments/management/main.tf`: thứ tự module, output dùng cho KUBECONFIG/ArgoCD.
- Mở `terraform/modules/vpc/main.tf`: tên SG (k8s_common, k8s_master, k8s_worker). Ghi VPC CIDR: Management `10.0.0.0/16`, Dev `10.1.0.0/16`, Prod `10.2.0.0/16`.

---

## Giai đoạn 1: Terraform – Dev/Prod chỉ còn EC2 + Docker

### 1.1 Tạo module Docker host

**1.1.1** Tạo thư mục `terraform/modules/docker-host/` với: `main.tf`, `variables.tf`, `outputs.tf`, `userdata_docker.sh`.

**1.1.2** `variables.tf`: `name_prefix`, `environment`, `instance_count`, `instance_type`, `ami_id`, `private_subnet_ids`, `security_group_ids`, `key_name`, `docker_tcp_port` (default 2376).

**1.1.3** `userdata_docker.sh`:
- `apt-get update -y`, cài Docker (repo chính thức hoặc `docker.io`).
- `systemctl enable docker && systemctl start docker`.
- Cấu hình `/etc/docker/daemon.json`: `{"hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2376"]}` (hoặc 2375), rồi `systemctl restart docker`.
- (Tùy chọn) `usermod -aG docker ubuntu`.

**1.1.4** `main.tf`: `aws_instance` với `count = var.instance_count`, `user_data = templatefile("${path.module}/userdata_docker.sh", { docker_tcp_port = var.docker_tcp_port })`, subnet round-robin, tag `Name = "${var.name_prefix}-docker-host-${count.index + 1}-${var.environment}"`.

**1.1.5** `outputs.tf`: `instance_ids`, `private_ips` (list IP cho DockerHost CRD).

### 1.2 Security group cho Docker host
- Trong module VPC (hoặc SG riêng): tạo SG `docker_host_sg`:
  - Ingress: port 22 từ OpenVPN/VPN CIDR; port **2376** (hoặc 2375) từ **CIDR VPC Management** (`10.0.0.0/16`).
  - Egress: 0.0.0.0/0.
- Thêm biến `management_vpc_cidr` vào VPC module; ở Dev/Prod truyền `["10.0.0.0/16"]`.

### 1.3 Sửa Dev
- **Xóa/comment**: `module "rke2"`, mọi `aws_lb_target_group_attachment` gắn master/worker với NLB và ALB.
- **Thêm**: gọi module vpc với `management_vpc_cidr = ["10.0.0.0/16"]`; gọi `module "docker_host"` với `source = "../../modules/docker-host"`, `environment = "dev"`, `instance_count` = 2, `instance_type` = "t2.small", `private_subnet_ids` = module.vpc, `security_group_ids` = [k8s_common_sg_id, docker_host_sg_id], `key_name` = module.keys.
- **Output**: `docker_host_private_ips` = module.docker_host.private_ips.
- **NLB/ALB**: Xóa NLB 6443; xóa attachment ALB tới RKE2. Giữ ALB nếu vẫn dùng (sau sẽ trỏ target tới docker-host).

### 1.4 Sửa Prod
- Giống 1.3: xóa RKE2 + attachment; thêm docker-host module, output `docker_host_private_ips`; vpc với `management_vpc_cidr`; xóa NLB 6443 và attachment ALB tới RKE2.

### 1.5 VPC Peering
- Không đổi; peering Management ↔ Dev/Prod đã đủ để Operator (Management) reach private IP Dev/Prod.

### 1.6 Apply
- `terraform -chdir=terraform/environments/dev plan -out=dev.tfplan` rồi `apply`.
- Làm tương tự Prod. Ghi lại IP: `terraform -chdir=terraform/environments/dev output -json docker_host_private_ips` (và prod).

---

## Giai đoạn 2: RKE2 chỉ ở Management + cài Operator

### 2.1 Management
- Không đổi module RKE2 trong `terraform/environments/management/main.tf`.

### 2.2 Đưa manifest Operator vào repo
- Tạo `k8s_helm/k8s-docker-operator/`, copy `install/install.yaml` từ repo [minhtri1612/k8s-docker](https://github.com/minhtri1612/k8s-docker) vào `install.yaml`.

### 2.3 configure.py
- Sau bước cài ArgoCD (chỉ khi `TERRAFORM_ENV == "management"`): thêm bước `kubectl apply -f k8s_helm/k8s-docker-operator/install.yaml` (dùng KUBECONFIG đúng cluster Management).
- Kiểm tra: `kubectl get pods -n system`, `kubectl get crd | grep kdop`.

---

## Giai đoạn 3: DockerHost + App (DockerContainer / DockerService)

### 3.1 DockerHost
- Tạo manifest DockerHost (Helm hoặc raw YAML) cho Dev và Prod: mỗi EC2 Docker = 1 DockerHost, `spec.hostURL: "tcp://<private_ip>:2376"`, `spec.tlsSecretName` trống nếu chưa TLS. IP lấy từ Terraform output (values/file).

### 3.2 Chuyển app từ Deployment sang CRD
- Với mỗi app: tạo DockerContainer (`spec.dockerHostRef`, `image`, `containerName`, `ports`, `envVars`, `volumeMounts`, `restartPolicy`); tạo DockerService (`spec.containerRef`, `spec.ports`) để expose. Xóa Deployment cũ.

### 3.3 ALB
- **Cách B (đơn giản):** ALB target group attach tới **instance_id** của module docker-host, port app (vd 3000). SG docker host mở port đó từ ALB. Traffic: user → ALB → EC2 Docker.

---

## Giai đoạn 4: ArgoCD
- Application cho Dev (DockerHost + DockerContainer + DockerService); Application cho Prod. RBAC/VPN giữ nguyên (dev user sync Dev, admin sync Prod).

---

## Giai đoạn 5: Kiểm tra
- Management: `kubectl get pods -n system`, `kubectl get dockerhosts -A` (phase Connected).
- SSH vào EC2 Docker: `docker ps`, `ss -tlnp | grep 2376`.
- App: `kubectl get dockercontainers`, `kubectl get dockerservices`; truy cập qua ALB.

---

## Giai đoạn 6: Cleanup & tài liệu
- Xóa code Terraform đã comment; cập nhật README (kiến trúc mới, version Operator, link repo).

---

## Checklist

| # | Bước | ☐ |
|---|------|---|
| 0 | Backup, branch, đọc cấu trúc & CIDR | |
| 1.1 | Module docker-host (main, variables, outputs, userdata_docker.sh) | |
| 1.2 | SG docker host (port 2376 từ Management CIDR) | |
| 1.3 | Dev: bỏ RKE2 + attachment, thêm docker-host, output IP | |
| 1.4 | Prod: tương tự Dev | |
| 1.5 | Peering/route | |
| 1.6 | Terraform apply Dev/Prod, ghi IP | |
| 2.1 | Management giữ RKE2 | |
| 2.2 | Copy install.yaml vào k8s_helm/k8s-docker-operator/ | |
| 2.3 | configure.py: cài Operator sau ArgoCD (chỉ management) | |
| 3.1 | DockerHost manifest + inject IP từ Terraform | |
| 3.2 | App: DockerContainer + DockerService, xóa Deployment | |
| 3.3 | ALB attachment tới docker-host instance | |
| 4 | ArgoCD Application Dev/Prod, RBAC/VPN | |
| 5 | Test Operator, DockerHost, app qua ALB | |
| 6 | Cleanup, README | |