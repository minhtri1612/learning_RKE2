#!/usr/bin/env bash
# ============================================================
# Đăng ký cluster với ArgoCD bằng cách tạo Secret trực tiếp trên management cluster.
# Không cần argocd CLI hay port-forward — chỉ dùng kubectl.
#
# Usage:
#   bash scripts/create-argocd-cluster-secrets.sh [dev|prod]
#
# Yêu cầu:
#   - VPN đang bật (để kubectl tới được management + dev/prod)
#   - ArgoCD đang chạy trên management cluster
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MGMT_KUBECONFIG="$ROOT_DIR/kube_config_rke2_management.yaml"

if [[ ! -f "$MGMT_KUBECONFIG" ]]; then
  echo "Error: Management kubeconfig not found: $MGMT_KUBECONFIG"
  echo "Chạy provision.py management + configure.py management trước."
  exit 1
fi

# Kiểm tra management cluster reachable (tránh lỗi "failed to download openapi" / i/o timeout)
MGMT_SERVER=$(kubectl --kubeconfig="$MGMT_KUBECONFIG" config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || true)
if [[ -z "$MGMT_SERVER" ]]; then
  echo "Error: Không đọc được server từ $MGMT_KUBECONFIG"
  exit 1
fi
if ! kubectl --kubeconfig="$MGMT_KUBECONFIG" get ns default --request-timeout=10s >/dev/null 2>&1; then
  echo "Error: Không kết nối được management cluster tại $MGMT_SERVER"
  echo "  - Master management đã bị terminated? Chạy: terraform -chdir=terraform/environments/management apply -auto-approve -var-file=terraform.tfvars"
  echo "  - Sau khi master mới lên, cập nhật kubeconfig (IP mới): lấy từ terraform output hoặc SCP từ node mới."
  echo "  - Bật VPN nếu đang dùng VPN để vào VPC."
  exit 1
fi

# ── Register cluster: tạo SA + token trên target cluster, rồi tạo Secret trên management ──
register_cluster() {
  local env="$1"
  local kubeconfig_file="$ROOT_DIR/kube_config_rke2_${env}.yaml"

  if [[ ! -f "$kubeconfig_file" ]]; then
    echo "  ⚠ Skipping $env: kubeconfig not found at $kubeconfig_file"
    return 0
  fi

  echo ""
  echo "Registering cluster: $env"
  echo "  Kubeconfig: $kubeconfig_file"

  local server_url
  server_url=$(kubectl --kubeconfig="$kubeconfig_file" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
  echo "  Server: $server_url"

  # 1. Trên target cluster: tạo SA + token cho Argo CD
  export KUBECONFIG="$kubeconfig_file"
  local sa_name="argocd-manager"
  local sa_ns="kube-system"

  kubectl create namespace "$sa_ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl create serviceaccount "$sa_name" -n "$sa_ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl create clusterrolebinding "argocd-manager-$env" \
    --clusterrole=cluster-admin \
    --serviceaccount="$sa_ns:$sa_name" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1

  local token
  token=$(kubectl create token "$sa_name" -n "$sa_ns" --duration=8760h 2>/dev/null) || true
  if [[ -z "$token" ]]; then
    echo "  ✗ Could not create token on $env cluster. Check VPN and cluster access."
    return 1
  fi

  # 2. Lấy CA từ kubeconfig (nếu có); không thì dùng insecure
  local ca_b64
  ca_b64=$(kubectl --kubeconfig="$kubeconfig_file" config view --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null) || true

  # 3. Tạo Secret trên management cluster
  export KUBECONFIG="$MGMT_KUBECONFIG"
  local secret_name="cluster-$env"
  local config_json
  if command -v jq >/dev/null 2>&1; then
    if [[ -n "$ca_b64" ]]; then
      config_json=$(jq -n --arg bt "$token" --arg ca "$ca_b64" '{bearerToken: $bt, tlsClientConfig: {insecure: false, caData: $ca}}')
    else
      config_json=$(jq -n --arg bt "$token" '{bearerToken: $bt, tlsClientConfig: {insecure: true}}')
    fi
  else
    if [[ -n "$ca_b64" ]]; then
      config_json=$(printf '{"bearerToken":"%s","tlsClientConfig":{"insecure":false,"caData":"%s"}}' "$token" "$ca_b64")
    else
      config_json=$(printf '{"bearerToken":"%s","tlsClientConfig":{"insecure":true}}' "$token")
    fi
  fi

  kubectl create secret generic "$secret_name" -n argocd \
    --from-literal=name="$env" \
    --from-literal=server="$server_url" \
    --from-literal=config="$config_json" \
    --dry-run=client -o yaml |
    kubectl label -f - --local -o yaml argocd.argoproj.io/secret-type=cluster |
    kubectl apply -f -

  echo "  ✓ Cluster '$env' registered with ArgoCD (Secret $secret_name)"
}

# ── Verify ────────────────────────────────────────────────────────────────────
verify_clusters() {
  echo ""
  echo "Registered cluster secrets:"
  kubectl get secret -n argocd -l argocd.argoproj.io/secret-type=cluster -o wide 2>/dev/null || true
}

# ── Main ──────────────────────────────────────────────────────────────────────
ENVS_TO_PROCESS="${1:-dev prod}"

for env in $ENVS_TO_PROCESS; do
  register_cluster "$env"
done

verify_clusters

echo ""
echo "Done! ArgoCD applications should start syncing now."
echo "Check: kubectl get applications -n argocd"
echo ""
echo "NOTE: Credentials live in ArgoCD Secrets on management cluster (NOT in Git)."
echo "      kubectl get secret -n argocd -l argocd.argoproj.io/secret-type=cluster"
