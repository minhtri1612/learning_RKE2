#!/usr/bin/env bash
# Xóa toàn bộ hạ tầng: dev → prod → management
# Chạy từ repo root: bash scripts/destroy-all-envs.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR/terraform"

echo "=============================================="
echo "  DESTROY: dev → prod → management"
echo "=============================================="

for env in dev prod management; do
  echo ""
  echo "--- Destroy $env ---"
  terraform -chdir="environments/$env" destroy -auto-approve -var-file=terraform.tfvars || {
    echo "  ⚠ Destroy $env failed (continuing...)"
  }
done

echo ""
echo "=============================================="
echo "  ✅ Done. To recreate: ./provision.py management, then dev, then prod."
echo "=============================================="
