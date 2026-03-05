#!/usr/bin/env bash
# Đồng bộ password dev: database + app-credentials dùng CÙNG một password
# (giống fix prod – tránh P1000 Authentication failed).
#
# Chạy trên máy có: aws CLI, jq, KUBECONFIG trỏ dev cluster (hoặc truyền qua --kubeconfig).
# Usage:
#   export KUBECONFIG=/path/to/kube_config_rke2_dev.yaml   # trước khi chạy phần kubectl
#   ./scripts/sync-dev-db-and-backend-secrets.sh           # chỉ cập nhật AWS
#   ./scripts/sync-dev-db-and-backend-secrets.sh --cluster # AWS + xóa secret K8s + xóa job migration trên dev
set -e

DEV_DB_PASSWORD="${DEV_DB_PASSWORD:-your-dev-db-password-here}"
RUN_CLUSTER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cluster) RUN_CLUSTER=1; shift ;;
    *) shift ;;
  esac
done

echo "=== Dev: đồng bộ database + app-credentials (password: ${DEV_DB_PASSWORD}) ==="

# 1) AWS: /meo-stationery/dev/database
echo "Updating AWS /meo-stationery/dev/database..."
aws secretsmanager put-secret-value \
  --secret-id "/meo-stationery/dev/database" \
  --secret-string "{
    \"POSTGRES_USER\": \"meo_admin\",
    \"POSTGRES_PASSWORD\": \"${DEV_DB_PASSWORD}\",
    \"POSTGRES_DB\": \"meo_stationery\"
  }"

# 2) AWS: meo-stationery/dev/app-credentials-v2 (DATABASE_URL cùng password)
echo "Updating AWS meo-stationery/dev/app-credentials-v2 (DATABASE_URL)..."
# URL-encode nếu password có ký tự đặc biệt
DATABASE_URL="postgresql://meo_admin:${DEV_DB_PASSWORD}@postgres.database.svc.cluster.local:5432/meo_stationery?schema=public"
# Nếu có ký tự đặc biệt thì dùng python
if command -v python3 &>/dev/null; then
  DATABASE_URL=$(python3 -c "import urllib.parse, os; p=os.environ.get('DEV_DB_PASSWORD','$DEV_DB_PASSWORD'); print('postgresql://meo_admin:' + urllib.parse.quote_plus(p) + '@postgres.database.svc.cluster.local:5432/meo_stationery?schema=public')")
fi
aws secretsmanager get-secret-value \
  --secret-id "meo-stationery/dev/app-credentials-v2" \
  --query SecretString --output text \
  | jq --arg url "$DATABASE_URL" '.DATABASE_URL = $url' > /tmp/app-creds-dev.json
aws secretsmanager put-secret-value \
  --secret-id "meo-stationery/dev/app-credentials-v2" \
  --secret-string file:///tmp/app-creds-dev.json

echo "AWS dev secrets updated."

if [[ -n "$RUN_CLUSTER" ]]; then
  echo "=== Dev cluster: xóa K8s secrets để ESO tạo lại, xóa migration job ==="
  kubectl -n database delete secret meo-stationery-database-secrets-dev --ignore-not-found=true
  kubectl -n meo-stationery delete secret meo-stationery-backend-secrets-dev --ignore-not-found=true
  echo "Đợi ~15s cho ESO sync..."
  sleep 15
  kubectl -n meo-stationery delete job meo-station-backend-dev-migration --ignore-not-found=true
  echo "Done. Vào ArgoCD sync lại meo-station-backend-dev. Nếu vẫn P1000 thì restart Postgres: kubectl -n database rollout restart statefulset postgres"
else
  echo "Chạy trên dev cluster (KUBECONFIG=.../kube_config_rke2_dev.yaml):"
  echo "  kubectl -n database delete secret meo-stationery-database-secrets-dev"
  echo "  kubectl -n meo-stationery delete secret meo-stationery-backend-secrets-dev"
  echo "  sleep 15"
  echo "  kubectl -n meo-stationery delete job meo-station-backend-dev-migration"
  echo "Rồi ArgoCD → meo-station-backend-dev → Sync."
fi
