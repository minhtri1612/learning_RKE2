# DockerHost manifests (Dev / Prod)

Mỗi EC2 Docker host (Dev/Prod) = 1 resource `DockerHost`. Operator chạy trên cluster **Management** kết nối tới Docker daemon qua `tcp://<private_ip>:2376` (VPC peering).

## Cách dùng

1. **Sau khi `terraform apply` Dev và Prod**, lấy private IP:

   ```bash
   terraform -chdir=terraform/environments/dev output -json docker_host_private_ips
   terraform -chdir=terraform/environments/prod output -json docker_host_private_ips
   ```

2. **Sửa tay** trong `dockerhost-dev.yaml` và `dockerhost-prod.yaml`: thay `REPLACE_DEV_IP_1`, `REPLACE_DEV_IP_2` (và prod) bằng IP thật từ output trên.

3. **Apply lên cluster Management** (đã cài K8s Docker Operator):

   ```bash
   export KUBECONFIG=/path/to/kube_config_rke2_management.yaml
   kubectl apply -f k8s_helm/k8s-docker-operator/docker-hosts/dockerhost-dev.yaml
   kubectl apply -f k8s_helm/k8s-docker-operator/docker-hosts/dockerhost-prod.yaml
   ```

4. **Kiểm tra:** `kubectl get dockerhosts -A` (Phase = Connected khi đã nối được Docker daemon).

## Tên DockerHost

- Dev: `dev-docker-host-1`, `dev-docker-host-2`, ...
- Prod: `prod-docker-host-1`, `prod-docker-host-2`, ...

Trong `DockerContainer` dùng `spec.dockerHostRef: "dev-docker-host-1"` (hoặc tên tương ứng).

## TLS

Nếu bật TLS cho Docker daemon, tạo Secret `ca.pem`/`cert.pem`/`key.pem` và set `spec.tlsSecretName` trên DockerHost. Để trống = không TLS.
