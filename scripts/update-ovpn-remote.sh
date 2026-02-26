#!/usr/bin/env bash
# Cập nhật dòng "remote" trong mọi file .ovpn theo IP OpenVPN server hiện tại (terraform output).
# Dùng khi VPN báo "TLS key negotiation failed" — thường do .ovpn trỏ IP cũ (server đã recreate / EIP đổi).
# Chạy từ repo root: ./scripts/update-ovpn-remote.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Cập nhật .ovpn theo IP OpenVPN server (Terraform management) ==="
OPENVPN_IP=""
STATE_DIR="terraform/environments/management"
# Thử terraform output trước
if [[ -f "$STATE_DIR/terraform.tfstate" ]]; then
  OPENVPN_IP=$(terraform -chdir="$STATE_DIR" output -raw openvpn_public_ip 2>/dev/null || true)
fi
# Nếu chưa có IP hợp lệ, đọc từ state JSON (vd. management_state.json)
if [[ ! "$OPENVPN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ -f "$STATE_DIR/management_state.json" ]]; then
  OPENVPN_IP=$(jq -r '.values.outputs.openvpn_public_ip.value // empty' "$STATE_DIR/management_state.json" 2>/dev/null || true)
fi
if [[ ! "$OPENVPN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "  ✗ Không lấy được openvpn_public_ip. Chạy: ./provision.py management"
  exit 1
fi
echo "  OpenVPN server IP (Terraform): $OPENVPN_IP"

OVPN_FILES=()
while IFS= read -r -d '' f; do OVPN_FILES+=("$f"); done < <(find "$REPO_ROOT" -maxdepth 1 -name "*.ovpn" -print0 2>/dev/null)
if [[ ${#OVPN_FILES[@]} -eq 0 ]]; then
  echo "  ✗ Không tìm thấy file .ovpn trong thư mục gốc. Chạy: ./provision.py management (để tạo .ovpn)"
  exit 1
fi

UPDATED=0
for f in "${OVPN_FILES[@]}"; do
  name=$(basename "$f")
  current=$(grep -E '^remote ' "$f" 2>/dev/null | head -1 || true)
  if [[ "$f" == *-tcp.ovpn ]]; then
    if [[ "$current" == "remote $OPENVPN_IP 443" ]]; then
      echo "  ⏭ $name — đã đúng remote $OPENVPN_IP 443"
    else
      sed -i "s/^remote .* 443/remote $OPENVPN_IP 443/" "$f"
      echo "  ✓ $name — đã đổi thành remote $OPENVPN_IP 443"
      UPDATED=1
    fi
  else
    if [[ "$current" == "remote $OPENVPN_IP 1194" ]]; then
      echo "  ⏭ $name — đã đúng remote $OPENVPN_IP 1194"
    else
      sed -i "s/^remote .* 1194/remote $OPENVPN_IP 1194/" "$f"
      echo "  ✓ $name — đã đổi thành remote $OPENVPN_IP 1194"
      UPDATED=1
    fi
  fi
done

echo ""
if [[ $UPDATED -eq 1 ]]; then
  echo "  Khởi động lại VPN: sudo openvpn --config sep_tong.ovpn  (hoặc sep_tong-tcp.ovpn nếu UDP bị chặn)"
  echo "  Nếu vẫn lỗi TLS: server có thể đã recreate (CA/cert mới). Chạy: ./scripts/refresh-ovpn.sh  (cần SSH tới server)"
else
  echo "  Nếu vẫn lỗi TLS: thử ./scripts/refresh-ovpn.sh  để tạo lại .ovpn từ server; hoặc thử TCP: sudo openvpn --config sep_tong-tcp.ovpn"
fi
