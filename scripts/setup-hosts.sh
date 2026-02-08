#!/usr/bin/env bash
# Chạy 1 lần sau ./deploy.py (env=management) nếu /etc/hosts chưa được cập nhật: sudo bash /home/minhtri/Downloads/practice_RKE2/scripts/setup-hosts.sh
set -e
ENTRY="3.24.84.64	argocd.local"
# Xóa dòng cũ có các host này
sudo sed -i.bak -E '/argocd\.local/d' /etc/hosts
echo "$ENTRY" | sudo tee -a /etc/hosts
echo "Done. Hosts for management: argocd.local"
