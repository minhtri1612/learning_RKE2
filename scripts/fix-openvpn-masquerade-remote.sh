#!/usr/bin/env bash
# Chạy trên máy BẠN (laptop). SSH vào EC2 OpenVPN và sửa MASQUERADE (AWS ens5 vs eth0).
# Dùng khi: curl https://<master-private>:6443 timeout dù VPN đã route qua tun0.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF="$ROOT/terraform"
KEY="${OPENVPN_SSH_KEY:-$TF/environments/management/k8s-key.pem}"
if [[ ! -f "$KEY" ]]; then
  echo "Không thấy key: $KEY — đặt OPENVPN_SSH_KEY=/path/to/k8s-key.pem" >&2
  exit 1
fi
IP="${OPENVPN_PUBLIC_IP:-}"
if [[ -z "$IP" ]]; then
  IP="$(terraform -chdir="$TF/environments/management" output -raw openvpn_public_ip 2>/dev/null || true)"
fi
if [[ -z "$IP" ]]; then
  echo "Thiếu IP. Ví dụ: OPENVPN_PUBLIC_IP=52.x.x.x $0" >&2
  exit 1
fi

echo "SSH ubuntu@$IP (key $KEY) và áp dụng MASQUERADE + rp_filter trên SERVER OpenVPN..."
ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -i "$KEY" "ubuntu@$IP" 'sudo bash -s' <<'REMOTE'
set -e
for i in eth0 ens5 ens4 ens3 enp0s3 enp0s8; do
  while iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o "$i" -j MASQUERADE 2>/dev/null; do :; done
done
iptables -t nat -C POSTROUTING -s 10.8.0.0/24 ! -d 10.8.0.0/24 -j MASQUERADE 2>/dev/null || \
  iptables -t nat -A POSTROUTING -s 10.8.0.0/24 ! -d 10.8.0.0/24 -j MASQUERADE
sysctl -w net.ipv4.conf.all.rp_filter=2 net.ipv4.conf.default.rp_filter=2 >/dev/null
iptables -t mangle -C FORWARD -p tcp -m tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || \
  iptables -t mangle -A FORWARD -p tcp -m tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
mkdir -p /etc/iptables
iptables-save | sudo tee /etc/iptables/rules.v4 >/dev/null
echo "OK trên $(hostname). Kiểm tra: sudo iptables -t nat -L POSTROUTING -n -v"
iptables -t nat -L POSTROUTING -n -v | head -20
REMOTE
echo
echo "Trên laptop: ngắt VPN rồi bật lại sep_tong-tcp.ovpn, sau đó:"
echo "  curl -k --connect-timeout 5 https://<master-private-ip>:6443/readyz"
echo "  (IP master: terraform -chdir=terraform/environments/management output -raw master_private_ip — dạng list thì dùng output -json)"
