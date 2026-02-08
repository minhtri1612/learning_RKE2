#!/usr/bin/env bash
# Tự động add cluster prod/dev vào ArgoCD (management).
# Dùng kết nối trực tiếp qua VPC Peering (Master Private IP).
# Chạy từ thư mục gốc project. Cần: argocd CLI, terraform output management + dev/prod.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"

# Set SSH opts to be non-interactive
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes"

# Management SSH Key
MGMT_KEY="$TERRAFORM_DIR/environments/management/k8s-key.pem"

cd "$ROOT_DIR"

if ! command -v argocd &>/dev/null; then
  echo "Lỗi: Chưa cài argocd CLI."
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "Lỗi: Chưa cài jq."
  exit 1
fi

# Login ArgoCD nếu có biến môi trường (hoặc tự login tay trước)
if [[ -n "${ARGOCD_PASSWORD:-}" ]]; then
  echo "Login ArgoCD..."
  argocd login argocd.local --insecure --grpc-web --username admin --password "$ARGOCD_PASSWORD" || true
fi

# Lấy Management Public IP (để SSH vào chạy lệnh nếu cần, nhưng script này giả định chạy TRÊN MÁY MANAGEMENT hoặc có VPN)
# Tuy nhiên, script này được thiết kế để chạy từ Local, SSH vào Management, rồi từ Management gọi lệnh argocd add cluster tới IP Private.
# Nhưng ở deploy.py hiện tại, chúng ta đang chạy script này TRÊN LOCAL (hoặc trong container deploy).
# Nếu chạy trên local, ta cần strategy:
# 1. SSH vào Management.
# 2. Từ Management, chạy lệnh argocd cluster add tới Private IP (10.x.x.x).
#    (Vì Management và Dev/Prod thông nhau qua Peering).

# Hàm lấy Management OpenVPN IP (đóng vai trò Jump host / Management Node IP)
get_management_ip() {
  local out
  out="$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/management" output -json 2>/dev/null)" || true
  echo "$out" | jq -r '.openvpn_public_ip.value // empty'
}

MGMT_IP="$(get_management_ip)"
if [[ -z "$MGMT_IP" ]]; then
  echo "Không tìm thấy Management IP. Kiểm tra terraform management."
  exit 1
fi

echo "Management IP: $MGMT_IP"

add_cluster_remote() {
  local env="$1"
  echo "Processing $env..."

  # Lấy thông tin dev/prod từ terraform
  local out_json
  out_json="$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -json 2>/dev/null)" || true
  
  if [[ -z "$out_json" ]]; then
    echo "  ⏭ Bỏ qua $env (không có output terraform)"
    return 0
  fi

  local master_ip
  master_ip="$(echo "$out_json" | jq -r '.master_private_ip.value[0] // empty')"
  
  if [[ -z "$master_ip" ]]; then
    echo "  ⏭ Bỏ qua $env (không tìm thấy master private ip)"
    return 0
  fi

  echo "  Target Master IP: $master_ip (Private)"

  # 1. Copy key của env lên Management (nếu chưa có)
  local env_key="$TERRAFORM_DIR/environments/$env/k8s-key.pem"
  if [[ -f "$env_key" ]]; then
    scp -i "$MGMT_KEY" $SSH_OPTS "$env_key" "ubuntu@${MGMT_IP}:~/.ssh/k8s-key-${env}.pem" >/dev/null
    ssh -i "$MGMT_KEY" $SSH_OPTS "ubuntu@${MGMT_IP}" "chmod 600 ~/.ssh/k8s-key-${env}.pem"
  else
    echo "  ⚠ Không tìm thấy key local: $env_key"
    return 1
  fi

  # 2. SSH vào Management để tạo/sửa kubeconfig và chạy argocd add
  #    Lệnh này chạy HOÀN TOÀN trên Management server.
  
  echo "  [Remote Management] Preparing kubeconfig for $env..."
  ssh -i "$MGMT_KEY" $SSH_OPTS "ubuntu@${MGMT_IP}" "bash -s" <<EOF
    set -e
    # Create .kube directory if it doesn't exist
    mkdir -p ~/.kube
    
    # Lấy kubeconfig từ master $env về management
    # Dùng SSH từ Management -> $master_ip (VPC Peering)
    ssh -i ~/.ssh/k8s-key-${env}.pem $SSH_OPTS ubuntu@${master_ip} "sudo cat /etc/rancher/rke2/rke2.yaml" > ~/.kube/config-${env}
    
    # Sửa kubeconfig:
    # - Server: $master_ip (Private IP)
    # - Remove CA verification (dùng insecure-skip-tls-verify)
    sed -i -e 's/127.0.0.1/${master_ip}/g' \\
           -e '/certificate-authority-data/d' \\
           -e '/server: https/a \\    insecure-skip-tls-verify: true' \\
           ~/.kube/config-${env}
    
    chmod 600 ~/.kube/config-${env}
    
    echo "  [Remote Management] Adding cluster $env to ArgoCD..."
    # Login ArgoCD (local trên management) nếu chưa logic
    # Giả định argocd cli đã cài (deploy.py đã cài)
    # Thử login nếu chưa (đỡ lỗi) - password lấy từ secret hoặc env, ở đây ta hardcode tạm hoặc bỏ qua nếu đã login
    
    # Chạy lệnh add
    # Lưu ý: cần echo y để confirm đè config nếu có
    echo y | argocd cluster add default --name ${env} --kubeconfig ~/.kube/config-${env} --yes --grpc-web || echo "⚠ Failed to add cluster"
EOF

  echo "  ✓ $env processed."
}

for env in prod dev; do
  add_cluster_remote "$env"
done

echo "Done adding clusters directly."
