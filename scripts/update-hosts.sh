#!/bin/bash
# Script wrapper để update /etc/hosts với ALB domains
# Usage: ./scripts/update-hosts.sh [dev|prod|management|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

ENV="${1:-all}"

echo "=== Auto-updating /etc/hosts for ALB domains ==="
echo "Environment: $ENV"
echo

# Check if terraform directories exist
if [ "$ENV" = "all" ]; then
    ENVS=("management" "dev" "prod")
else
    ENVS=("$ENV")
fi

for e in "${ENVS[@]}"; do
    if [ ! -d "terraform/environments/$e" ]; then
        echo "⚠️  Environment $e not found, skipping..."
        continue
    fi
    
    if [ ! -f "terraform/environments/$e/terraform.tfstate" ]; then
        echo "⚠️  No terraform state for $e, skipping..."
        continue
    fi
    
    echo "Processing $e environment..."
    python3 scripts/update-hosts.py "$e"
    echo
done

echo "=== Done ==="
echo "You can now access:"
echo "  - ArgoCD: http://argocd.local (management)"
echo "  - Dev App: https://meo-stationery-dev.local (dev)"
echo "  - Prod App: https://meo-stationery-prod.local (prod)"
echo "  - Rancher: https://rancher.local (management/prod)"
echo
echo "Note: HTTPS uses self-signed certificates, expect browser warnings."