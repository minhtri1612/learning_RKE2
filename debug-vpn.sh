#!/bin/bash
# Chạy sau khi start VPN service. Kiểm tra: service có chạy? route 10.0.x qua tun? .ovpn trùng IP server?
set -e
cd "$(dirname "$0")"
echo "=== 1. VPN service status ==="
systemctl status openvpn-practice-rke2 --no-pager 2>/dev/null || true
echo ""
echo "=== 2. Route to 10.0.101.0 (phải có 'dev tun' nếu VPN đã kết nối) ==="
ip route get 10.0.101.0 2>/dev/null || echo "(no route)"
echo ""
echo "=== 3. .ovpn remote IP vs Terraform OpenVPN IP (phải trùng) ==="
echo -n "minhtri.ovpn remote: "
grep -E '^remote ' minhtri.ovpn 2>/dev/null || echo "(file not found)"
echo -n "Terraform openvpn_public_ip: "
(cd terraform && terraform output -raw openvpn_public_ip 2>/dev/null) || echo "(terraform not available)"
echo ""
echo -n "OpenVPN process đang kết nối tới (từ log): "
journalctl -u openvpn-practice-rke2 -n 50 --no-pager 2>/dev/null | grep -oE '\[AF_INET\][0-9.]+:1194' | tail -1 || echo "(không tìm thấy)"
echo ""
echo "=== 4. Last VPN service logs ==="
journalctl -u openvpn-practice-rke2 -n 15 --no-pager 2>/dev/null || true
