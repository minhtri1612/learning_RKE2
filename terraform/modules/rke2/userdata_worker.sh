#!/bin/bash
set -e

swapoff -a || true
sed -i 's/^\([^#].*swap.*\)$/# \1 # Disabled for RKE2/' /etc/fstab || true
modprobe overlay || true
modprobe br_netfilter || true
cat > /etc/sysctl.d/rke2.conf <<'SYSCTL'
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
SYSCTL
sysctl --system || true

MASTER_IP="${master_ip}"
echo "Waiting for master node at $MASTER_IP:9345 to be ready..."
timeout 600 bash -c 'until curl -k -s https://${master_ip}:9345 >/dev/null 2>&1 || nc -z ${master_ip} 9345; do sleep 10; done' || true

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sh -
mkdir -p /etc/rancher/rke2/
cat <<EOT > /etc/rancher/rke2/config.yaml
server: https://${master_ip}:9345
token: ${rke2_token}
EOT

systemctl enable rke2-agent
systemctl start rke2-agent
timeout 300 bash -c 'until systemctl is-active --quiet rke2-agent; do sleep 5; done' || true
