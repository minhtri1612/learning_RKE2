#!/usr/bin/env bash
# Reset Postgres dev: xóa data → DB khởi tạo lại với password từ secret (AWS đã set your-dev-db-password-here).
# Chạy khi đã chạy sync-dev-db-and-backend-secrets.sh (AWS + xóa secret) nhưng vẫn P1000.
#
# Cần: export KUBECONFIG=/path/to/kube_config_rke2_dev.yaml
set -e

NS_DB="database"
NS_APP="meo-stationery"
STS_NAME="postgres"
PVC_NAME="postgres-storage-postgres-0"

echo "1. Xóa secret để ESO tạo lại từ AWS (password: your-dev-db-password-here)"
kubectl -n "$NS_DB" delete secret meo-stationery-database-secrets-dev --ignore-not-found=true
kubectl -n "$NS_APP" delete secret meo-stationery-backend-secrets-dev --ignore-not-found=true
echo "   Đợi 15s cho ESO sync..."
sleep 15

echo "2. Scale Postgres xuống 0"
kubectl -n "$NS_DB" scale statefulset "$STS_NAME" --replicas=0
echo "   Đợi 15s cho pod tắt hẳn..."
sleep 15

echo "3. Xóa PVC (data Postgres dev — MẤT DATA)"
kubectl -n "$NS_DB" delete pvc "$PVC_NAME" --ignore-not-found=true

echo "4. Scale Postgres lên 1 (khởi tạo lại với password mới)"
kubectl -n "$NS_DB" scale statefulset "$STS_NAME" --replicas=1

echo "5. Xóa migration job để ArgoCD tạo lại khi Sync"
kubectl -n "$NS_APP" delete job meo-station-backend-dev-migration --ignore-not-found=true

echo ""
echo "Đợi ~30s cho Postgres init xong, rồi ArgoCD → meo-station-backend-dev → Sync."
