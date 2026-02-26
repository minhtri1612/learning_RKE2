#!/usr/bin/env bash
# Cập nhật .ovpn theo IP OpenVPN server hiện tại (terraform output).
# Chạy Ansible để tạo lại .ovpn trên server và tải về. Dùng khi VPN TLS error do server đã recreate (CA/cert mới).
# Chạy từ repo root: ./scripts/refresh-ovpn.sh
# Cần: SSH tới OpenVPN server (IP từ terraform). Nếu chỉ đổi IP mà server không đổi, dùng ./scripts/update-ovpn-remote.sh
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

OPENVPN_IP=$(terraform -chdir=terraform/environments/management output -raw openvpn_public_ip 2>/dev/null || true)
if [[ ! "$OPENVPN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ -f terraform/environments/management/management_state.json ]]; then
  OPENVPN_IP=$(jq -r '.values.outputs.openvpn_public_ip.value // empty' terraform/environments/management/management_state.json 2>/dev/null || true)
fi
if [[ ! "$OPENVPN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "✗ Không lấy được openvpn_public_ip. Chạy: ./provision.py management"
  exit 1
fi
echo "OpenVPN server (Management): $OPENVPN_IP"
echo "Current .ovpn remote: $(grep -E '^remote ' *.ovpn 2>/dev/null | head -1 || echo '?')"

mkdir -p ansible
echo "vpn_server:
  hosts:
    $OPENVPN_IP:" > ansible/inventory_openvpn.yml

KEY_FILE="$REPO_ROOT/terraform/environments/management/k8s-key.pem"
if [[ ! -f "$KEY_FILE" ]]; then
  echo "✗ Không tìm thấy key: $KEY_FILE"
  exit 1
fi

echo "Kiểm tra SSH tới $OPENVPN_IP (timeout 10s)..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=no -i "$KEY_FILE" ubuntu@"$OPENVPN_IP" exit 2>/dev/null; then
  echo ""
  echo "✗ SSH tới OpenVPN server timeout / bị từ chối."
  echo "  Security Group chỉ cho phép SSH từ my_ip (terraform)."
  echo ""
  echo "  Cách 1 – Mở SSH từ mọi nơi (tạm thời):"
  echo "    Trong terraform/environments/management/terraform.tfvars đặt:"
  echo "      my_ip = \"0.0.0.0/0\""
  echo "    Rồi: cd terraform/environments/management && terraform apply"
  echo ""
  echo "  Cách 2 – Chỉ cho IP hiện tại của bạn:"
  echo "    MY_IP=\$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
  echo "    Trong terraform.tfvars đặt: my_ip = \"\${MY_IP}/32\""
  echo "    Rồi terraform apply, xong chạy lại ./scripts/refresh-ovpn.sh"
  echo ""
  exit 1
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_PRIVATE_KEY_FILE="$KEY_FILE"
cd ansible
if ! ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip="$OPENVPN_IP" openvpn-server.yml; then
  echo ""
  echo "✗ Ansible thất bại. Nếu lỗi UNREACHABLE: kiểm tra SSH (my_ip trong terraform.tfvars + terraform apply)."
  exit 1
fi
cd "$REPO_ROOT"
echo ""
echo "✓ .ovpn đã tạo lại và tải về."
echo "  Thử UDP: sudo openvpn --config sep_tong.ovpn"
echo "  Nếu vẫn lỗi TLS, thử TCP: sudo openvpn --config sep_tong-tcp.ovpn"
echo "  (Mở TCP 443 trên AWS SG nếu chưa: cd terraform/environments/management && terraform apply)"
