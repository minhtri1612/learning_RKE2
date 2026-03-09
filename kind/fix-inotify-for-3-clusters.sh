#!/usr/bin/env bash
# Tăng giới hạn inotify trên host Linux để chạy được 3 Kind cluster
# (fix lỗi kubelet connection refused :10248 / "too many open files")
# Chạy: ./kind/fix-inotify-for-3-clusters.sh   hoặc   bash kind/fix-inotify-for-3-clusters.sh

set -e
echo "Đang thêm fs.inotify.* vào /etc/sysctl.conf (cần sudo)..."
echo "fs.inotify.max_user_watches=655360" | sudo tee -a /etc/sysctl.conf
echo "fs.inotify.max_user_instances=1280" | sudo tee -a /etc/sysctl.conf
echo "Áp dụng ngay: sudo sysctl -p"
sudo sysctl -p
echo "Xong. Thử tạo lại cluster thứ 3: kind create cluster --name prod --config kind/prod-kind-config.yaml"
