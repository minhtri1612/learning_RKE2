#!/usr/bin/env bash
# Cập nhật file argocd/clusters/cluster-<env>.yaml từ kubeconfig (KHÔNG cần VPN / kubectl).
# Sau khi chạy provision.py dev (hoặc prod), chạy script này rồi git add + push.
# ArgoCD sync từ Git sẽ nhận IP mới.
# Usage: ./scripts/update-argocd-cluster-manifest-from-kubeconfig.sh [dev|prod]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

env="${1:-}"
if [[ -z "$env" || "$env" != "dev" && "$env" != "prod" ]]; then
  echo "Usage: $0 dev|prod"
  exit 1
fi

kubeconfig_file="$ROOT_DIR/kube_config_rke2_${env}.yaml"
if [[ ! -f "$kubeconfig_file" ]]; then
  echo "Không tìm thấy $kubeconfig_file. Chạy provision.py $env trước."
  exit 1
fi

server=$(yq eval '.clusters[0].cluster.server' "$kubeconfig_file")
client_cert=$(yq eval '.users[0].user.client-certificate-data' "$kubeconfig_file")
client_key=$(yq eval '.users[0].user.client-key-data' "$kubeconfig_file")

if [[ -z "$server" || "$server" == "null" ]]; then
  echo "Không đọc được server từ kubeconfig."
  exit 1
fi

manifest_file="$ROOT_DIR/argocd/clusters/cluster-${env}.yaml"
if [[ ! -f "$manifest_file" ]]; then
  echo "Không tìm thấy $manifest_file"
  exit 1
fi

yq eval ".stringData.server = \"${server}\"" -i "$manifest_file"
python3 - "$manifest_file" "$client_cert" "$client_key" <<'PYEOF'
import sys, json, re
manifest_path, cert, key = sys.argv[1], sys.argv[2], sys.argv[3]
config = json.dumps({"tlsClientConfig": {"insecure": True, "certData": cert, "keyData": key}})
with open(manifest_path, 'r') as f:
    content = f.read()
if 'config:' in content:
    content = re.sub(r"(\s+config:).*", f"\\1 '{config}'", content, count=1)
else:
    content = content.rstrip('\n') + f"\n  config: '{config}'\n"
with open(manifest_path, 'w') as f:
    f.write(content)
PYEOF

echo "✓ Đã cập nhật argocd/clusters/cluster-${env}.yaml → server=$server"
echo "  Bước tiếp: git add argocd/clusters/ && git commit -m 'fix: cluster ${env} IP' && git push"
echo "  Sau khi push, ArgoCD sẽ sync secret mới (hoặc trên management: kubectl delete secret cluster-${env} -n argocd để ép tạo lại)."
