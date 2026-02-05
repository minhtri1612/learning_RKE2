#!/usr/bin/env bash
# Cập nhật .ovpn theo IP OpenVPN server hiện tại (terraform output).
# Dùng khi VPN báo TLS error vì .ovpn trỏ IP cũ (server đã recreate).
# Chạy từ repo root: ./scripts/refresh-ovpn.sh
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

OPENVPN_IP=$(cd terraform && terraform -chdir=environments/management output -raw openvpn_public_ip)
echo "OpenVPN server (Management): $OPENVPN_IP"
echo "minhtri.ovpn remote: $(grep -E '^remote ' minhtri.ovpn 2>/dev/null || echo '?')"

mkdir -p ansible
echo "vpn_server:
  hosts:
    $OPENVPN_IP:" > ansible/inventory_openvpn.yml

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_PRIVATE_KEY_FILE="$REPO_ROOT/terraform/environments/management/k8s-key.pem"
cd ansible
ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip="$OPENVPN_IP" openvpn-server.yml
cd "$REPO_ROOT"
echo ""
echo "✓ .ovpn đã cập nhật. Khởi động lại VPN:"
echo "  sudo systemctl restart openvpn-practice-rke2"
echo "  journalctl -u openvpn-practice-rke2 -f"
