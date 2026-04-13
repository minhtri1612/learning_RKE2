#!/usr/bin/env bash
# Đồng bộ remote_write URL (Prometheus Agent workload → Prometheus management) — không hardcode IP trong Git.
#
# Cách dùng:
#   ./scripts/sync-monitoring-remote-write-url.sh              # đọc IP từ Docker
#   MGMT_PROMETHEUS_REMOTE_WRITE_URL='http://x:32090/api/v1/write' ./scripts/sync-monitoring-remote-write-url.sh
#   ./scripts/sync-monitoring-remote-write-url.sh --print-only # chỉ in URL write
#   ./scripts/sync-monitoring-remote-write-url.sh --print-ready-url
#   ./scripts/sync-monitoring-remote-write-url.sh --check        # GET /-/ready từ máy host
#   ./scripts/sync-monitoring-remote-write-url.sh --help
#
# Biến môi trường:
#   MGMT_PROMETHEUS_REMOTE_WRITE_URL  — bỏ qua Docker, set URL đầy đủ
#   MGMT_CONTROL_PLANE_CONTAINER        — mặc định: management-control-plane
#   MGMT_PROMETHEUS_NODEPORT            — mặc định: 32090
#   MONITORING_WORKLOAD_VALUES          — mặc định: monitoring/monitoring-workload.yaml (đường dẫn tương đối repo)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/${MONITORING_WORKLOAD_VALUES:-monitoring/monitoring-workload.yaml}"
CONTAINER_NAME="${MGMT_CONTROL_PLANE_CONTAINER:-management-control-plane}"
NODEPORT="${MGMT_PROMETHEUS_NODEPORT:-32090}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

resolve_url() {
  if [[ -n "${MGMT_PROMETHEUS_REMOTE_WRITE_URL:-}" ]]; then
    echo "${MGMT_PROMETHEUS_REMOTE_WRITE_URL}"
    return 0
  fi
  if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
    echo "Không tìm thấy container Docker '$CONTAINER_NAME'." >&2
    echo "Đặt MGMT_PROMETHEUS_REMOTE_WRITE_URL hoặc MGMT_CONTROL_PLANE_CONTAINER." >&2
    exit 1
  fi
  # Nhiều network: lấy IP đầu tiên
  local raw
  raw="$(docker inspect "$CONTAINER_NAME" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}')"
  local ip
  ip="$(echo "$raw" | awk '{print $1}')"
  if [[ -z "$ip" ]]; then
    echo "Không đọc được IP của $CONTAINER_NAME" >&2
    exit 1
  fi
  echo "http://${ip}:${NODEPORT}/api/v1/write"
}

write_ready_url() {
  local w="$1"
  echo "${w%/api/v1/write}/-/ready"
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
  code="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 "$ready" || true)"
  echo "GET $ready → HTTP $code"
  [[ "$code" == "200" ]] && exit 0
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
  # URL chuẩn http://IP:port/api/v1/write không chứa ký tự đặc biệt của sed khi dùng | làm delimiter
  sed -i "s|^[[:space:]]*- url: http://[^[:space:]]*api/v1/write|      - url: ${URL}|" "$TARGET"
fi

echo "Đã ghi remote_write URL: $URL"
echo "File: $TARGET"
echo "Kiểm tra: $0 --check"
