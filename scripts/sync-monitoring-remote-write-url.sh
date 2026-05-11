#!/usr/bin/env bash
# Đồng bộ remote_write URL (Prometheus Agent workload → Prometheus management) — không hardcode IP trong Git.
#
# Cách dùng:
#   ./scripts/sync-monitoring-remote-write-url.sh              # đọc IP từ terraform/environments/management
#   MGMT_PROMETHEUS_REMOTE_WRITE_URL='http://x:32090/api/v1/write' ./scripts/sync-monitoring-remote-write-url.sh
#   ./scripts/sync-monitoring-remote-write-url.sh --print-only
#   ./scripts/sync-monitoring-remote-write-url.sh --print-ready-url
#   ./scripts/sync-monitoring-remote-write-url.sh --check
#   ./scripts/sync-monitoring-remote-write-url.sh --commit-push
#   ./scripts/sync-monitoring-remote-write-url.sh --help
#
# Biến môi trường:
#   MGMT_PROMETHEUS_REMOTE_WRITE_URL  — bỏ qua terraform, set URL đầy đủ
#   MGMT_PROMETHEUS_NODEPORT          — mặc định: 32090
#   MONITORING_WORKLOAD_VALUES        — mặc định: monitoring/monitoring-workload.yaml
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/${MONITORING_WORKLOAD_VALUES:-monitoring/monitoring-workload.yaml}"
NODEPORT="${MGMT_PROMETHEUS_NODEPORT:-32090}"
CHECK_RETRIES="${MGMT_READY_CHECK_RETRIES:-12}"
CHECK_SLEEP_SECONDS="${MGMT_READY_CHECK_SLEEP_SECONDS:-5}"

COMMIT_PUSH=false
argv=()
for arg in "$@"; do
  if [[ "$arg" == --commit-push ]]; then
    COMMIT_PUSH=true
    continue
  fi
  argv+=("$arg")
done
set -- "${argv[@]}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

resolve_url() {
  if [[ -n "${MGMT_PROMETHEUS_REMOTE_WRITE_URL:-}" ]]; then
    echo "${MGMT_PROMETHEUS_REMOTE_WRITE_URL}"
    return 0
  fi
  local tf_dir="${ROOT}/terraform"
  if [[ ! -d "${tf_dir}/environments/management" ]]; then
    echo "Không thấy ${tf_dir}/environments/management." >&2
    echo "Đặt MGMT_PROMETHEUS_REMOTE_WRITE_URL hoặc chạy terraform apply cho management." >&2
    exit 1
  fi
  if ! command -v terraform &>/dev/null; then
    echo "Cần terraform trên PATH hoặc đặt MGMT_PROMETHEUS_REMOTE_WRITE_URL." >&2
    exit 1
  fi
  local tf_json
  tf_json="$(cd "$tf_dir" && terraform -chdir=environments/management output -json 2>/dev/null || true)"
  if [[ -z "$tf_json" ]]; then
    echo "Không đọc được terraform output management (init/apply chưa?)." >&2
    echo "Đặt MGMT_PROMETHEUS_REMOTE_WRITE_URL hoặc: cd terraform/environments/management && terraform init" >&2
    exit 1
  fi
  local ip
  ip="$(echo "$tf_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
w = (d.get('worker_private_ips') or {}).get('value') or []
m = (d.get('master_private_ip') or {}).get('value') or []
node = (w or m or [None])[0]
print(node or '', end='')
" 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then
    echo "Terraform management không có worker_private_ips / master_private_ip." >&2
    echo "Đặt MGMT_PROMETHEUS_REMOTE_WRITE_URL." >&2
    exit 1
  fi
  echo "http://${ip}:${NODEPORT}/api/v1/write"
}

write_ready_url() {
  local w="$1"
  echo "${w%/api/v1/write}/-/ready"
}

git_commit_push_values() {
  local rel="${TARGET#$ROOT/}"
  if [[ "$rel" == "$TARGET" ]] || [[ "$rel" == /* ]]; then
    echo "Không suy ra đường dẫn tương đối cho git add (TARGET ngoài ROOT?)." >&2
    exit 1
  fi
  cd "$ROOT"
  if ! git rev-parse --git-dir &>/dev/null; then
    echo "Thư mục không phải git repo: $ROOT" >&2
    exit 1
  fi
  git add -- "$rel"
  if git diff --cached --quiet; then
    echo "Git: không có thay đổi để commit (URL đã trùng hoặc file không đổi)."
  else
    git commit -m "chore(monitoring): sync remote_write URL for RKE2 management"
  fi
  git push
  echo "Git: đã push (hoặc remote đã up to date)."
}

case "${1:-}" in
  --help|-h) usage ;;
esac

PRINT_ONLY=false
PRINT_READY=false
CHECK=false
[[ "${1:-}" == "--print-only" ]] && PRINT_ONLY=true
[[ "${1:-}" == "--print-ready-url" ]] && PRINT_READY=true
[[ "${1:-}" == "--check" ]] && CHECK=true

URL="$(resolve_url)"

if $PRINT_ONLY; then
  echo "$URL"
  exit 0
fi

if $PRINT_READY; then
  write_ready_url "$URL"
  exit 0
fi

if $CHECK; then
  ready="$(write_ready_url "$URL")"
  code=""
  for i in $(seq 1 "$CHECK_RETRIES"); do
    code="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 "$ready" || true)"
    echo "[$i/$CHECK_RETRIES] GET $ready → HTTP $code"
    if [[ "$code" == "200" ]]; then
      exit 0
    fi
    sleep "$CHECK_SLEEP_SECONDS"
  done
  echo "Prometheus management chưa sẵn sàng sau $CHECK_RETRIES lần thử." >&2
  if command -v kubectl &>/dev/null; then
    kc="${ROOT}/kube_config_rke2_management.yaml"
    echo "Gợi ý chẩn đoán (VPN + KUBECONFIG=$kc):" >&2
    echo "  kubectl --kubeconfig=$kc -n monitoring get pods" >&2
    echo "  kubectl --kubeconfig=$kc -n monitoring get svc -o wide | head" >&2
  fi
  exit 1
fi

if [[ ! -f "$TARGET" ]]; then
  echo "Không thấy file: $TARGET" >&2
  exit 1
fi

if command -v yq &>/dev/null; then
  yq -i ".prometheus.prometheusSpec.remoteWrite[0].url = \"${URL}\"" "$TARGET"
else
  if ! grep -q 'api/v1/write' "$TARGET"; then
    echo "Không tìm thấy dòng remote_write trong $TARGET" >&2
    exit 1
  fi
  sed -i "s|^[[:space:]]*- url: http://[^[:space:]]*api/v1/write|      - url: ${URL}|" "$TARGET"
fi

echo "Đã ghi remote_write URL: $URL"
echo "File: $TARGET"
echo "Kiểm tra: $0 --check"

if $COMMIT_PUSH; then
  git_commit_push_values
fi
