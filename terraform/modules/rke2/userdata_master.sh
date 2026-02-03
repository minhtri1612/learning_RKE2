#!/bin/bash
set -e

# System Preparation
swapoff -a || true
sed -i 's/^\([^#].*swap.*\)$/# \1 # Disabled for RKE2/' /etc/fstab || true
modprobe overlay || true
modprobe br_netfilter || true
cat > /etc/sysctl.d/rke2.conf <<'SYSCTL'
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
SYSCTL
sysctl --system || true

# RKE2 Server Installation
INSTANCE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="server" sh -
mkdir -p /etc/rancher/rke2/
cat <<EOT > /etc/rancher/rke2/config.yaml
token: ${rke2_token}
write-kubeconfig-mode: "0644"
tls-san:
  - "${nlb_dns}"
  - "$INSTANCE_IP"
EOT

systemctl enable rke2-server
systemctl start rke2-server
timeout 300 bash -c 'until systemctl is-active --quiet rke2-server && curl -k -s https://localhost:6443/readyz >/dev/null 2>&1; do sleep 5; done' || true

mkdir -p /home/ubuntu/.kube
cp /etc/rancher/rke2/rke2.yaml /home/ubuntu/.kube/config
chown -R ubuntu:ubuntu /home/ubuntu/.kube
cat > /etc/profile.d/rke2.sh <<'PROFILE'
export PATH=$PATH:/var/lib/rancher/rke2/bin
if [ -f "$HOME/.kube/config" ]; then export KUBECONFIG="$HOME/.kube/config"; elif [ -f "/etc/rancher/rke2/rke2.yaml" ]; then export KUBECONFIG="/etc/rancher/rke2/rke2.yaml"; fi
PROFILE
chmod +x /etc/profile.d/rke2.sh
ln -sf /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/kubectl
ln -sf /var/lib/rancher/rke2/bin/crictl /usr/local/bin/crictl
ln -sf /var/lib/rancher/rke2/bin/ctr /usr/local/bin/ctr
echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> /home/ubuntu/.bashrc
mkdir -p /root/.kube
cp /etc/rancher/rke2/rke2.yaml /root/.kube/config
mkdir -p /etc/rancher/rke2/kubeconfig
cp /etc/rancher/rke2/rke2.yaml /etc/rancher/rke2/kubeconfig/config
export PATH=$PATH:/var/lib/rancher/rke2/bin
