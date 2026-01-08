#!/bin/bash
# Quick status check script

echo "=== Checking Master Node ==="
MASTER_IP="52.63.70.0"
WORKER_IP="3.27.227.140"
KEY_FILE="./terraform/k8s-key.pem"

echo "Master: $MASTER_IP"
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP << 'EOF'
echo "--- RKE2 Server Status ---"
sudo systemctl status rke2-server --no-pager -l | head -20
echo ""
echo "--- kubectl nodes ---"
export PATH=$PATH:/var/lib/rancher/rke2/bin
kubectl get nodes 2>/dev/null || echo "kubectl not available or cluster not ready"
EOF

echo ""
echo "=== Checking Worker Node ==="
echo "Worker: $WORKER_IP"
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@$WORKER_IP << 'EOF'
echo "--- RKE2 Agent Status ---"
sudo systemctl status rke2-agent --no-pager -l | head -20
echo ""
echo "--- Agent Config ---"
cat /etc/rancher/rke2/config.yaml 2>/dev/null || echo "Config file not found"
echo ""
echo "--- Recent Agent Logs ---"
sudo journalctl -u rke2-agent -n 20 --no-pager 2>/dev/null || echo "No logs"
EOF

echo ""
echo "=== Done ==="








