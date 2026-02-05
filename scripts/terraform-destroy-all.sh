#!/usr/bin/env bash
# Destroy từng env một, đợi xong rồi mới env tiếp (tránh lock + tránh Ctrl+C giữa chừng).
# Thứ tự: networking trước (peering + routes), rồi dev -> prod -> management.
# Lưu ý: networking dùng data lookup route table; nếu mgmt/dev/prod đã destroy trước thì
# module networking đã dùng aws_route_tables + count nên vẫn destroy được (chỉ xóa peering).
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/terraform"

for env in networking dev prod management; do
  if [[ ! -d "environments/$env" ]]; then
    echo "⏭ Bỏ qua $env (không có thư mục)"
    continue
  fi
  echo "=============================================="
  echo "Destroy $env (đợi xong, không Ctrl+C)..."
  echo "=============================================="
  terraform -chdir="environments/$env" destroy -auto-approve
  echo "✓ $env destroy xong."
done
echo "Done. Tất cả env đã destroy."
