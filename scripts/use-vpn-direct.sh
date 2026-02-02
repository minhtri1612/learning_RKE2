#!/usr/bin/env bash
# Cập nhật server trong kube_config_rke2.yaml theo master IP hiện tại (terraform output).
# Dùng khi đã recreate infra và master IP đổi — chạy từ repo root: ./scripts/use-vpn-direct.sh
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
MASTER_IP=$(cd terraform && terraform output -json master_private_ip | python3 -c "import sys,json; print(json.load(sys.stdin)[0])")
if [ ! -f kube_config_rke2.yaml ]; then
  echo "kube_config_rke2.yaml not found. Run ./deploy.py first."
  exit 1
fi
sed -i.bak "s|server: https://[^ ]*|server: https://${MASTER_IP}:6443|" kube_config_rke2.yaml
echo "Updated kube_config_rke2.yaml (server: https://${MASTER_IP}:6443)"
echo "  export KUBECONFIG=$REPO_ROOT/kube_config_rke2.yaml"
echo "  ssh -i terraform/k8s-key.pem ubuntu@${MASTER_IP}"
