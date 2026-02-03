#!/usr/bin/env bash
# Force recreate OpenVPN instance (fix SSH timeout when instance was in wrong subnet / state).
# Sau khi chạy xong, chạy lại: ./deploy.py dev

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${1:-dev}"

cd "$ROOT_DIR/terraform"
EXTRA=""
[ -f "environments/$ENV/terraform.tfvars" ] && EXTRA="-var-file=terraform.tfvars"
terraform -chdir=environments/"$ENV" apply \
  -replace="module.openvpn.aws_instance.openvpn" \
  -auto-approve -input=false $EXTRA

echo ""
echo "✓ OpenVPN instance recreated. Đợi ~1–2 phút rồi chạy: ./deploy.py $ENV"
