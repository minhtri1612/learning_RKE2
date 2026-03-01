#!/bin/bash
# -----------------------------------------------------------------------------
# User data for Docker-only EC2 (Dev/Prod). No RKE2.
# Configures Docker daemon to listen on TCP so K8s Docker Operator (Management)
# can connect via tcp://<private_ip>:${docker_tcp_port}
# -----------------------------------------------------------------------------
set -e

export DEBIAN_FRONTEND=noninteractive

# Install Docker (Ubuntu 22.04)
apt-get update -y
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$${VERSION_CODENAME:-jammy}") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io

systemctl enable docker
systemctl start docker

# Configure Docker to listen on TCP (for Operator in Management VPC)
# Port 2376 = default with TLS; 2375 = without TLS. Use 2376 as default.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://${docker_tcp_bind}:${docker_tcp_port}"]
}
EOF
systemctl restart docker

# Allow ubuntu user to run docker without sudo
usermod -aG docker ubuntu || true

# Log for debugging
echo "Docker userdata completed at $(date). Listening on tcp://${docker_tcp_bind}:${docker_tcp_port}" >> /var/log/userdata-docker.log
