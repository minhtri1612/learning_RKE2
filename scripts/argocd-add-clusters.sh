#!/usr/bin/env bash
# Tự động add cluster prod/dev vào ArgoCD (management).
# Dùng SSH tunnel qua OpenVPN Management (một jump host) → dev/prod không có OpenVPN.
# Chạy từ thư mục gốc project. Cần: argocd CLI, đã login ArgoCD (hoặc set ARGOCD_PASSWORD), terraform output management + dev/prod.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/terraform"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"
# Key và OpenVPN chỉ từ Management
MGMT_KEY="$TERRAFORM_DIR/environments/management/k8s-key.pem"
declare -A LOCAL_PORTS=( ["prod"]=6447 ["dev"]=6448 )
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

cd "$ROOT_DIR"

if ! command -v argocd &>/dev/null; then
  echo "Lỗi: Chưa cài argocd CLI. Chạy: curl -sSL -o /tmp/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64 && chmod +x /tmp/argocd && sudo mv /tmp/argocd /usr/local/bin/"
  exit 1
fi
if ! command -v jq &>/dev/null; then
  echo "Lỗi: Chưa cài jq. Chạy: sudo apt install -y jq"
  exit 1
fi

# Login ArgoCD nếu có password (tránh hỏi tay)
if [[ -n "${ARGOCD_PASSWORD:-}" ]]; then
  echo "Login ArgoCD..."
  argocd login argocd.local --insecure --grpc-web --username admin --password "$ARGOCD_PASSWORD" || true
fi

# Lấy OpenVPN Management một lần (dev/prod không có OpenVPN)
get_management_openvpn_ip() {
  local out
  out="$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/management" output -json 2>/dev/null)" || true
  echo "$out" | jq -r '.openvpn_public_ip.value // empty'
}

add_cluster() {
  local env="$1"
  local kc="$ROOT_DIR/kube_config_rke2_${env}.yaml"
  if [[ ! -f "$kc" ]]; then
    echo "  ⏭ Bỏ qua $env (chưa có $kc)"
    return 0
  fi
  local out_json
  out_json="$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -json 2>/dev/null)" || true
  if [[ -z "$out_json" ]]; then
    echo "  ⏭ Bỏ qua $env (chưa có terraform output)"
    return 0
  fi
  local master_ip
  master_ip="$(echo "$out_json" | jq -r '.master_private_ip.value[0] // .master_private_ip.value // empty')"
  if [[ -z "$master_ip" ]]; then
    echo "  ⏭ Bỏ qua $env (thiếu master_private_ip)"
    return 0
  fi
  local openvpn_ip
  openvpn_ip="$(get_management_openvpn_ip)"
  if [[ -z "$openvpn_ip" ]]; then
    echo "  ⏭ Bỏ qua $env (chưa có Management OpenVPN - chạy terraform apply management trước)"
    return 0
  fi
  if [[ ! -f "$MGMT_KEY" ]]; then
    echo "  ⏭ Bỏ qua $env (chưa có $MGMT_KEY)"
    return 0
  fi
  chmod 600 "$MGMT_KEY" 2>/dev/null || true

  local port="${LOCAL_PORTS[$env]:-6447}"
  pkill -f "ssh -L ${port}:" 2>/dev/null || true
  echo "  [$env] SSH tunnel (Management OpenVPN) $openvpn_ip -> 127.0.0.1:$port (master $master_ip:6443)..."
  ssh -L "${port}:${master_ip}:6443" -i "$MGMT_KEY" $SSH_OPTS "ubuntu@${openvpn_ip}" -N &
  local ssh_pid=$!
  PIDS+=( "$ssh_pid" )
  sleep 3
  if ! kill -0 "$ssh_pid" 2>/dev/null; then
    echo "  ⚠ [$env] Tunnel failed (SSH không kết nối được - kiểm tra Management OpenVPN / key)"
    return 1
  fi

  local tmp_kc
  tmp_kc="$(mktemp)"
  sed "s|server: https://[^:]*:6443|server: https://127.0.0.1:${port}|" "$kc" > "$tmp_kc"
  echo "  [$env] argocd cluster add default --name $env ..."
  # Không ẩn stderr để thấy lỗi thật (cluster đã tồn tại, timeout, v.v.)
  if argocd cluster add default --name "$env" --kubeconfig "$tmp_kc" --yes --grpc-web; then
    echo "  ✓ [$env] Đã add cluster."
  else
    echo "  ⚠ [$env] argocd cluster add thất bại (xem lỗi argocd ở trên)."
  fi
  rm -f "$tmp_kc"
  kill "$ssh_pid" 2>/dev/null || true
  return 0
}

# Patch cluster server URL sang NLB để ArgoCD (chạy trong management cluster) sync được
patch_cluster_servers_to_nlb() {
  local kc_mgmt="$ROOT_DIR/kube_config_rke2_management.yaml"
  [[ ! -f "$kc_mgmt" ]] && return 0
  export KUBECONFIG="$kc_mgmt"
  for env in dev prod; do
    local nlb_url
    nlb_url="$(cd "$TERRAFORM_DIR" && terraform -chdir="environments/$env" output -raw cluster_api_url 2>/dev/null)" || true
    [[ -z "$nlb_url" ]] && continue
    local secret_name
    secret_name="$(kubectl get secrets -n argocd -l argocd.argoproj.io/secret-type=cluster -o json 2>/dev/null | jq -r --arg n "$env" '.items[] | select(.data.name != null) | select((.data.name | @base64d) == $n) | .metadata.name' 2>/dev/null)" || true
    if [[ -n "$secret_name" ]]; then
      local server_b64
      server_b64="$(echo -n "$nlb_url" | base64 -w 0)"
      if kubectl patch secret -n argocd "$secret_name" -p "{\"data\":{\"server\":\"$server_b64\"}}" 2>/dev/null; then
        echo "  ✓ [$env] Đã patch cluster server -> NLB (ArgoCD sync qua NLB)."
      fi
    fi
  done
}

echo "Add clusters vào ArgoCD (SSH tunnel qua OpenVPN Management)..."
for env in prod dev; do
  add_cluster "$env"
done
echo "Patch cluster server -> NLB (để ArgoCD trong management sync được)..."
patch_cluster_servers_to_nlb
echo "Done. Mở http://argocd.local -> Settings -> Clusters để kiểm tra."
