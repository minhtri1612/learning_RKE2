#!/usr/bin/env bash
# Sửa route VPN khi tun có peer sai (255.255.255.0).
# Chạy SAU KHI đã bật VPN (sudo openvpn --config xxx.ovpn).
# Cách dùng: sudo ./scripts/fix-vpn-routes.sh [tun0]
# Nếu không truyền tham số, script tự tìm interface tun đang up.

set -e
TUN="${1:-}"

if [[ -z "$TUN" ]]; then
  for t in /sys/class/net/tun*; do
    [[ -d "$t" ]] || continue
    n="$(basename "$t")"
    if ip link show "$n" 2>/dev/null | grep -q "state UNKNOWN"; then
      TUN="$n"
      break
    fi
  done
fi

if [[ -z "$TUN" ]] || ! ip link show "$TUN" &>/dev/null; then
  echo "Không tìm thấy interface tun. Chạy: sudo $0 tun0"
  exit 1
fi

GW="10.8.0.1"
echo "Dùng interface: $TUN, gateway: $GW"

for cidr in 10.0.0.0/16 10.1.0.0/16 10.2.0.0/16; do
  ip route replace "$cidr" via "$GW" dev "$TUN" 2>/dev/null || ip route add "$cidr" via "$GW" dev "$TUN"
  echo "  route $cidr via $GW dev $TUN"
done

echo "Xong. Thử: ping 10.0.101.77 (management)"
