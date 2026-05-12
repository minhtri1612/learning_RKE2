#!/usr/bin/env python3
"""
Phase 2 — CẦN VPN (VPN Required)
==================================
Cài đặt Kubernetes workloads: EBS CSI Driver, Argo CD (management),
External Secrets Operator (dev/prod).

Usage:
    ./configure.py [dev|prod|management]   (mặc định: management)
    ./configure.py prod --skip-vpn-check   (hiếm: bỏ probe TCP/curl đầu — **không** thay thế VPN; kubectl vẫn cần tới apiserver)

⚠️  Đảm bảo VPN đang bật trước khi chạy:
    sudo openvpn --config minhtri.ovpn
"""
import glob
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

# ── Cấu hình ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAFORM_DIR = os.path.join(_SCRIPT_DIR, "terraform")
HELM_DIR = os.path.join(_SCRIPT_DIR, "k8s_helm")

_VALID_ENVS = ("dev", "prod", "management")
SSH_KEY_FILE_NAME = "k8s-key.pem"

BACKEND_NAMESPACE = "meo-stationery"
DATABASE_NAMESPACE = "database"

# Khớp argocd/bootstrap/*-cilium-*.yaml — configure.py cài Cilium trước EBS/ArogCD khi RKE2 disable-kube-proxy.
CILIUM_CHART_VERSION = "1.19.2"
# Nếu bật CILIUM_HELM_WAIT=1: Helm --wait chờ cả Hubble/ClusterMesh/… (có thể rất lâu). Timeout: CILIUM_HELM_TIMEOUT (mặc định 45m).
_DEFAULT_CILIUM_HELM_TIMEOUT = "45m"
# Helm --timeout khi không --wait (hooks / apply manifest lên API).
_CILIUM_HELM_APPLY_TIMEOUT = "15m"
# Chờ cilium agent: không im lặng hàng chục phút — in pod/DS định kỳ. Giây (vd: CILIUM_ROLLOUT_TIMEOUT=3600).
_DEFAULT_CILIUM_ROLLOUT_SECONDS = 1200
_CILIUM_ROLLOUT_SLICE_S = 45
_CILIUM_ROLLOUT_LOG_INTERVAL_S = 40

HOSTNAMES_FOR_NLB_BY_ENV = {
    "management": ("argocd.local",),
    "dev": ("meo-stationery-dev.local",),
    "prod": ("meo-stationery-prod.local",),
}


def _strip_configure_argv_flags() -> None:
    """Loại --skip-vpn-check / -S khỏi argv (đặt SKIP_VPN_CHECK=1). Ví dụ: ./configure.py prod --skip-vpn-check"""
    if len(sys.argv) < 2:
        return
    new_argv = [sys.argv[0]]
    for arg in sys.argv[1:]:
        if arg in ("--skip-vpn-check", "-S"):
            os.environ["SKIP_VPN_CHECK"] = "1"
            continue
        new_argv.append(arg)
    if len(new_argv) != len(sys.argv):
        sys.argv[:] = new_argv


_strip_configure_argv_flags()


def _route_to_host_uses_tun0(host: str) -> bool:
    """True nếu ip route get host cho thấy traffic đi qua tun0."""
    r = subprocess.run(
        f"ip route get {shlex.quote(host)} 2>/dev/null",
        shell=True,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "").strip()
    return "dev tun0" in out


def _get_env():
    if len(sys.argv) >= 2:
        env = sys.argv[1].lower()
        if env in _VALID_ENVS:
            return env
        print(f"Usage: {sys.argv[0]} [dev|prod|management] [--skip-vpn-check]", file=sys.stderr)
        sys.exit(1)
    return os.environ.get("TF_ENV", "management")


TERRAFORM_ENV = _get_env()
TERRAFORM_ENV_DIR = os.path.join(TERRAFORM_DIR, "environments", TERRAFORM_ENV)
KUBECONFIG_FILE = os.path.join(_SCRIPT_DIR, f"kube_config_rke2_{TERRAFORM_ENV}.yaml")
APP_INGRESS_HOST = f"meo-stationery-{TERRAFORM_ENV}.local"


# ── Utilities ─────────────────────────────────────────────────────────────────
def run_command(command, cwd=None, env=None, timeout=None):
    """Chạy shell command, thoát nếu lỗi."""
    print(f"Running: {command}")
    try:
        subprocess.run(command, shell=True, cwd=cwd, env=env, check=True, timeout=timeout)
    except subprocess.CalledProcessError:
        print(f"Error running command: {command}")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"Command timed out: {command}")
        sys.exit(1)


def get_terraform_output():
    """Lấy terraform output dưới dạng JSON."""
    print("Fetching Terraform outputs...")
    cmd = f"terraform -chdir=environments/{TERRAFORM_ENV} output -json"
    output = subprocess.check_output(cmd, shell=True, cwd=TERRAFORM_DIR).decode("utf-8")
    return json.loads(output)


def _kubeconfig_for_deploy():
    return os.path.abspath(KUBECONFIG_FILE)


def _apply_argocd_projects_manifests(env):
    """`argocd/projects` là Helm chart — không được `kubectl apply -f` cả thư mục (Chart.yaml/values.yaml không phải manifest)."""
    chart_dir = os.path.join(_SCRIPT_DIR, "argocd", "projects")
    values_file = os.path.join(chart_dir, "values.yaml")
    chart_yaml = os.path.join(chart_dir, "Chart.yaml")
    if not os.path.isdir(chart_dir) or not os.path.isfile(chart_yaml):
        print("  ⚠ Bỏ qua Argo CD Projects — không thấy Helm chart tại argocd/projects.")
        return False
    if not os.path.isfile(values_file):
        print("  ⚠ Bỏ qua Argo CD Projects — thiếu values.yaml.")
        return False
    run_command(
        f"helm template argocd-projects {shlex.quote(chart_dir)} -f {shlex.quote(values_file)} | kubectl apply -f -",
        cwd=_SCRIPT_DIR,
        env=env,
        timeout=120,
    )
    return True


def _apply_argocd_rbac_manifests(env):
    """Chỉ apply *.yaml / *.yml phẳng trong argocd/rbac (bỏ qua thư mục rỗng / không phải manifest)."""
    rbac_dir = os.path.join(_SCRIPT_DIR, "argocd", "rbac")
    if not os.path.isdir(rbac_dir):
        return False
    files = sorted(
        glob.glob(os.path.join(rbac_dir, "*.yaml"))
        + glob.glob(os.path.join(rbac_dir, "*.yml"))
    )
    if not files:
        return False
    apply_args = " ".join(f"-f {shlex.quote(p)}" for p in files)
    run_command(f"kubectl apply {apply_args}", cwd=_SCRIPT_DIR, env=env, timeout=60)
    return True


def _apiserver_host_port_from_kubeconfig(kubeconfig_path):
    """Lấy (host, port) từ server: https://host:6443 trong kubeconfig."""
    try:
        with open(kubeconfig_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r"server:\s*https?://([^:/\s]+):(\d+)", text)
        if m:
            return m.group(1), int(m.group(2))
    except OSError:
        pass
    return None, None


def _tcp_probe(host, port, timeout_sec=8):
    """True nếu TCP tới host:port thành công (chỉ kiểm tra lớp mạng, không TLS)."""
    if not host or not port:
        return False
    try:
        s = socket.create_connection((host, port), timeout=timeout_sec)
        s.close()
        return True
    except OSError:
        return False


def _curl_apiserver_readyz_noproxy(host, port, timeout_sec=12) -> bool:
    """HTTPS /readyz, không đi qua HTTP proxy (IP 10.x bị proxy chặn rất hay gặp)."""
    if not shutil.which("curl"):
        return False
    url = f"https://{host}:{port}/readyz"
    ct = str(max(3, min(int(timeout_sec), 20)))
    mt = str(max(8, int(timeout_sec) + 3))
    r = subprocess.run(
        ["curl", "-k", "-sf", "--noproxy", "*", "--connect-timeout", ct, "--max-time", mt, url],
        capture_output=True,
        timeout=int(timeout_sec) + 15,
    )
    return r.returncode == 0


def _print_apiserver_connect_diagnostics(host: str) -> None:
    """Gợi ý khi VPN “đang bật” nhưng probe tới apiserver fail (WSL vs host, proxy, route)."""
    print("  --- chẩn đoán nhanh (cùng máy với terminal chạy configure) ---")
    subprocess.run(f"ip route get {shlex.quote(host)} 2>/dev/null || true", shell=True)
    subprocess.run("ip -br addr show tun0 2>/dev/null || echo '  (không có tun0 trên máy này — OpenVPN có đang chạy ở đây không?)'", shell=True)
    px = []
    for k in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        v = os.environ.get(k)
        if v:
            px.append(f"{k}={v[:80]}")
    if px:
        print("  ⚠ Đang có biến proxy trong môi trường (curl đã dùng --noproxy; vẫn nên kiểm tra):")
        for line in px[:6]:
            print(f"     {line}")
    print(
        "  → Hai terminal **cùng một máy** vẫn dùng **chung** tun0 và routing — mở OpenVPN ở terminal 1, "
        "curl/configure ở terminal 2 là **bình thường**, không phải lỗi “hai máy”."
    )
    print(
        "  → Nếu `ip route get` đã ra **dev tun0** mà HTTPS :6443 vẫn timeout: lỗi thường gặp là **Security Group** "
        "node RKE2 (chưa cho 6443 từ 10.8.0.0/24 hoặc từ private IP EC2 OpenVPN), **forward/NAT** trên server OpenVPN, "
        "hoặc tunnel lệch — thử **tắt rồi bật lại** client; trên EC2 OpenVPN: `curl -k https://<apiserver>:6443/readyz` và xem `iptables`/MASQUERADE."
    )
    print("  → WSL2: OpenVPN trên **Windows** không cho WSL route 10.x — chạy OpenVPN **trong** WSL hoặc chạy configure trên cùng OS với tun0.")
    print("  → Nếu shell là **SSH sang máy khác** (không phải hai tab local): máy SSH không có tun0 của laptop — phải VPN trên đúng máy đang gõ lệnh.")


def check_vpn_connectivity():
    """Kiểm tra VPN + API: TCP tới apiserver, rồi kubectl get nodes (có retry sau provision)."""
    if os.environ.get("SKIP_VPN_CHECK") == "1":
        print("  ⏭ SKIP_VPN_CHECK=1 — bỏ qua kiểm tra VPN.")
        return True

    kubeconfig_path = _kubeconfig_for_deploy()
    if not os.path.isfile(kubeconfig_path):
        print(f"  ✗ Không tìm thấy kubeconfig: {kubeconfig_path}")
        print(f"     Chạy trước: ./provision.py {TERRAFORM_ENV}")
        sys.exit(1)

    api_host, api_port = _apiserver_host_port_from_kubeconfig(kubeconfig_path)
    if api_host and api_port:
        print(
            f"  Kiểm tra tới apiserver {api_host}:{api_port} "
            f"(VPN + route; thêm curl --noproxy vì HTTP proxy hay chặn IP 10.x)..."
        )
        reach_ok = False
        for attempt in range(1, 4):
            if _tcp_probe(api_host, api_port, timeout_sec=10):
                reach_ok = True
                break
            if _curl_apiserver_readyz_noproxy(api_host, api_port, timeout_sec=14):
                reach_ok = True
                print("  (TCP probe fail nhưng curl --noproxy */readyz OK — tiếp tục.)")
                break
            if attempt < 3:
                print(f"  … Chưa tới được apiserver (lần {attempt}/3), thử lại sau 4s.")
                time.sleep(4)
        if not reach_ok:
            print("  ✗ Không tới được apiserver sau 3 lần (TCP + curl --noproxy).")
            _print_apiserver_connect_diagnostics(api_host)
            if _route_to_host_uses_tun0(api_host):
                script = os.path.basename(sys.argv[0])
                print()
                print("  ─────────────────────────────────────────────────────────────")
                print(
                    "  Route đã qua **tun0** mà :6443 vẫn timeout → đường tới apiserver đang **gãy** "
                    "(SG, NAT/iptables trên EC2 OpenVPN, tunnel stale). **Cách đúng:** sửa mạng + reconnect VPN."
                )
                print(
                    "  SKIP / --skip-vpn-check **không** thay OpenVPN: kubeconfig vẫn trỏ private IP; "
                    "chỉ bỏ bước kiểm tra sớm — nếu API thật sự không tới được, `kubectl`/`helm` ngay sau đó vẫn lỗi."
                )
                print(
                    "  Chỉ dùng khi bạn **chắc** đây là lỗi probe/CI đặc biệt (hiếm). Còn không thì đừng SKIP — fix OpenVPN/SG."
                )
                print(f"    SKIP_VPN_CHECK=1 ./{script} {TERRAFORM_ENV}   hoặc   ./{script} {TERRAFORM_ENV} --skip-vpn-check")
                print("  ─────────────────────────────────────────────────────────────")
            print("     → OpenVPN phải trên **cùng máy / cùng network namespace** với terminal chạy ./configure.py.")
            print(
                f"     → Thử tay: curl -k --noproxy '*' --connect-timeout 5 https://{api_host}:{api_port}/readyz"
            )
            sys.exit(1)
        print("  ✓ Tới apiserver OK (TCP hoặc HTTPS /readyz).")

    print("  Checking Kubernetes API (kubectl get nodes, có thể vài lần sau provision)...")
    kubectl_cmd = (
        f"kubectl --kubeconfig={shlex.quote(kubeconfig_path)} get nodes --request-timeout=20s"
    )
    last_err = ""
    for attempt in range(1, 9):
        try:
            res = subprocess.run(
                kubectl_cmd,
                shell=True,
                capture_output=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            last_err = "kubectl subprocess timeout (45s)"
            res = None
        else:
            if res.returncode == 0:
                print("  ✓ VPN/API OK — kubectl get nodes thành công.")
                return True
            last_err = (res.stderr or res.stdout or b"").decode(errors="replace").strip()[:400]

        if attempt < 8:
            print(f"  Thử lại {attempt}/8 sau 8s... ({last_err[:120] if last_err else 'timeout'})")
            time.sleep(8)

    print("  ✗ kubectl get nodes thất bại sau nhiều lần thử.")
    if last_err:
        print(f"     Lỗi: {last_err}")
    print("\n  ⚠️  Nếu VPN đang bật: đợi RKE2 ổn định rồi chạy lại, hoặc kiểm tra kubeconfig / chứng thư.")
    print(f"     Hoặc: SKIP_VPN_CHECK=1 ./configure.py {TERRAFORM_ENV}")
    sys.exit(1)


# ── Phase 2 Functions ─────────────────────────────────────────────────────────
def wait_for_nlb_health_checks():
    print("--- Waiting for NLB to become healthy (2 min) ---")
    time.sleep(120)


def wait_for_k8s_api(kubeconfig_path, max_wait=120):
    """Đợi API server sẵn sàng (kết nối qua OpenVPN)."""
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    print("  Waiting for Kubernetes API server to be accessible...")
    waited = 0
    last_error = ""
    while waited < max_wait:
        res = subprocess.run(
            f"kubectl --kubeconfig={kubeconfig_path} get nodes --request-timeout=15s",
            shell=True, capture_output=True, env=env, timeout=25,
        )
        if res.returncode == 0:
            print(f"  ✓ API server is accessible (waited {waited}s)")
            return True
        err = (res.stderr or b"").decode(errors="ignore").strip()
        if err and err != last_error:
            last_error = err
            if waited % 30 == 0:
                print(f"  Still waiting... ({err[:150]})")
        time.sleep(10)
        waited += 10
    print(f"  ✗ API server not accessible after {max_wait}s")
    return False


def _first_master_private_ip(tf_out):
    """IP master đầu tiên (terraform output) — dùng cho Cilium k8sServiceHost khi không có kube-proxy."""
    try:
        val = tf_out.get("master_private_ip", {}).get("value")
        if isinstance(val, list) and val:
            return val[0]
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None


def _patch_cilium_k8s_service_host(tf_out):
    """Ghi k8sServiceHost = IP master cluster hiện tại (terraform). RKE2 tắt kube-proxy: Cilium cần IP thật, không ClusterIP kubernetes."""
    placeholder = "PLACEHOLDER_MASTER_PRIVATE_IP"
    ip = _first_master_private_ip(tf_out)
    if not ip:
        print(f"  ⚠ Bỏ qua patch k8sServiceHost — không có master_private_ip trong terraform output.")
        return
    # k8sServiceHost theo từng cluster (dev/prod overlay khác nhau) — không patch cilium-values.yaml chung.
    if TERRAFORM_ENV == "management":
        targets = ("cilium-values-management.yaml",)
    elif TERRAFORM_ENV == "dev":
        targets = ("cilium-cluster-dev.yaml",)
    elif TERRAFORM_ENV == "prod":
        targets = ("cilium-cluster-prod.yaml",)
    else:
        targets = ()
    k8s_line_lit = re.compile(
        r"^(\s*k8sServiceHost:\s*)[\"']?((?:\d{1,3}\.){3}\d{1,3})[\"']?\s*$",
        re.MULTILINE,
    )

    for fname in targets:
        path = os.path.join(_SCRIPT_DIR, "cilium", fname)
        if not os.path.isfile(path):
            continue
        with open(path, "r") as f:
            content = f.read()
        if placeholder in content:
            new_content = content.replace(placeholder, ip)
        else:
            new_content, n_sub = k8s_line_lit.subn(rf'\1"{ip}"', content, count=1)
            if n_sub == 0:
                print(f"  ⚠ {fname}: không có {placeholder} hay k8sServiceHost IPv4 — bỏ qua.")
                continue
        if new_content == content:
            continue
        with open(path, "w") as f:
            f.write(new_content)
        print(f"  ✓ Patched {fname}: k8sServiceHost → {ip} (master_private_ip / {TERRAFORM_ENV})")


def _kubectl_rollout_if_exists(kind_name: str, namespace: str, timeout: str, env) -> None:
    """Chờ rollout chỉ khi object đã tồn tại (tránh lỗi khi chart không tạo resource)."""
    probe = subprocess.run(
        f"kubectl get {kind_name} -n {namespace} -o name",
        shell=True,
        env=env,
        capture_output=True,
    )
    if probe.returncode != 0 or not (probe.stdout or b"").strip():
        return
    print(f"  Chờ rollout {kind_name} (tối đa {timeout})...")
    run_command(
        f"kubectl rollout status {kind_name} -n {namespace} --timeout={timeout}",
        env=env,
    )


def _ds_cilium_ready_stats(env) -> tuple[int, int, int] | None:
    """(numberReady, desiredNumberScheduled, updatedNumberScheduled) hoặc None."""
    r = subprocess.run(
        "kubectl get daemonset cilium -n kube-system "
        '-o jsonpath="{.status.numberReady},{.status.desiredNumberScheduled},{.status.updatedNumberScheduled}"',
        shell=True,
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    raw = (r.stdout or "").strip().strip('"')
    if not raw or raw == ",":
        return None
    parts = raw.split(",")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _cilium_agent_rollout_requires_all_nodes(env) -> bool:
    """Management / CILIUM_STRICT_ROLLOUT: chờ full DS. Spoke dev/prod: mặc định chỉ cần ≥1 Ready."""
    if os.environ.get("CILIUM_STRICT_ROLLOUT", "").lower() in ("1", "true", "yes"):
        return True
    return TERRAFORM_ENV not in ("dev", "prod")


def _print_cilium_agent_pods(env) -> None:
    subprocess.run(
        "kubectl get pods -n kube-system -l k8s-app=cilium -o wide",
        shell=True,
        env=env,
    )


def _print_first_cilium_pod_tail_describe(env, lines: int = 60) -> None:
    subprocess.run(
        f"bash -c 'p=$(kubectl get pods -n kube-system -l k8s-app=cilium -o jsonpath=\"{{.items[0].metadata.name}}\" 2>/dev/null); "
        f"test -n \"$p\" && kubectl describe pod -n kube-system \"$p\" | tail -n {lines}'",
        shell=True,
        env=env,
    )


def _wait_cilium_agent(env) -> None:
    max_sec = int(os.environ.get("CILIUM_ROLLOUT_TIMEOUT", str(_DEFAULT_CILIUM_ROLLOUT_SECONDS)))
    require_full = _cilium_agent_rollout_requires_all_nodes(env)
    slice_s = _CILIUM_ROLLOUT_SLICE_S
    if require_full:
        print(
            f"  Chờ **toàn bộ** DaemonSet cilium (management hoặc CILIUM_STRICT_ROLLOUT=1). "
            f"Tối đa {max_sec}s; log mỗi ~{_CILIUM_ROLLOUT_LOG_INTERVAL_S}s."
        )
    else:
        print(
            f"  Chờ cilium agent (spoke: **≥1 pod Ready** là đủ; bật CILIUM_STRICT_ROLLOUT=1 nếu cần cả 3 node). "
            f"Tối đa {max_sec}s; log mỗi ~{_CILIUM_ROLLOUT_LOG_INTERVAL_S}s."
        )

    deadline = time.monotonic() + max_sec
    next_log = 0.0
    first = True
    while time.monotonic() < deadline:
        stats = _ds_cilium_ready_stats(env)
        if stats and not require_full and stats[0] >= 1:
            print(
                f"  ✓ Cilium agent numberReady={stats[0]} (desired={stats[1]}) — tiếp tục configure."
            )
            return

        now = time.monotonic()
        if first or now >= next_log:
            first = False
            next_log = now + _CILIUM_ROLLOUT_LOG_INTERVAL_S
            if stats:
                print(f"  … DaemonSet cilium: ready={stats[0]} desired={stats[1]} updated={stats[2]}")
            else:
                print("  … (chưa đọc được trạng thái DaemonSet cilium — DS vừa tạo?)")
            _print_cilium_agent_pods(env)

        r_roll = subprocess.run(
            f"kubectl rollout status daemonset/cilium -n kube-system --timeout={slice_s}s",
            shell=True,
            env=env,
            capture_output=True,
            text=True,
        )
        if r_roll.returncode == 0:
            stats2 = _ds_cilium_ready_stats(env)
            if require_full:
                ok = bool(
                    stats2 and stats2[1] > 0 and stats2[0] >= stats2[1]
                )  # numberReady >= desired
            else:
                ok = bool(stats2 and stats2[0] >= 1)
            if ok:
                print("  ✓ DaemonSet cilium rollout hoàn tất (numberReady khớp điều kiện).")
                return
            print(
                "  ⚠ kubectl rollout status đã exit 0 nhưng agent chưa Ready (DS có thể vừa đổi template) — tiếp tục chờ."
            )
        time.sleep(2)

    print(f"  ✗ Hết thời gian {max_sec}s — cilium agent vẫn chưa đạt điều kiện.")
    _print_cilium_agent_pods(env)
    print("  --- describe pod cilium (đoạn cuối) ---")
    _print_first_cilium_pod_tail_describe(env)
    print(
        "  Gợi ý: **k8sServiceHost** phải là IP private master **đúng cluster/VPC** (RKE2 tắt kube-proxy) — sai → Init:CrashLoop; "
        "hoặc ImagePull/node NotReady; CILIUM_ROLLOUT_TIMEOUT=3600 nếu chỉ pull chậm."
    )
    sys.exit(1)


def _wait_cilium_operator(env) -> None:
    op_deadline = time.monotonic() + int(os.environ.get("CILIUM_OPERATOR_ROLLOUT_SECONDS", "600"))
    next_log = 0.0
    while time.monotonic() < op_deadline:
        r = subprocess.run(
            "kubectl rollout status deployment/cilium-operator -n kube-system --timeout=60s",
            shell=True,
            env=env,
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            r2 = subprocess.run(
                "kubectl get deploy cilium-operator -n kube-system -o jsonpath='{.status.readyReplicas}'",
                shell=True,
                env=env,
                capture_output=True,
                text=True,
            )
            try:
                ready = int((r2.stdout or "").strip() or "0")
            except ValueError:
                ready = 0
            if ready >= 1:
                print("  ✓ cilium-operator rollout hoàn tất (readyReplicas≥1).")
                return
            print(
                "  ⚠ rollout status exit 0 nhưng readyReplicas chưa ≥1 — tiếp tục chờ."
            )
        if time.monotonic() >= next_log:
            next_log = time.monotonic() + 50
            print("  … cilium-operator:")
            subprocess.run(
                "kubectl get deploy cilium-operator -n kube-system -o wide; "
                "kubectl get pods -n kube-system -l name=cilium-operator -o wide 2>/dev/null || true",
                shell=True,
                env=env,
            )
        time.sleep(2)
    print("  ✗ Timeout chờ cilium-operator.")
    subprocess.run(
        "kubectl describe deploy cilium-operator -n kube-system | tail -40",
        shell=True,
        env=env,
    )
    sys.exit(1)


def _build_cilium_value_files(
    cilium_dir: str, include_bootstrap: bool, include_clustermesh: bool = True
) -> list[str]:
    """Return ordered list of Cilium Helm value files for the current environment.

    include_bootstrap=True  → append spoke-bootstrap override file (step 1 only).
    include_clustermesh=False → skip clustermesh-management-peer.yaml (step 1 only:
        ClusterMesh tries to connect to the hub cluster during init; with empty BPF
        policy maps that can trigger additional host-endpoint policy checks that drop
        traffic before maps are fully loaded).
    """
    bootstrap_file = "cilium-values-spoke-bootstrap.yaml"
    if TERRAFORM_ENV == "management":
        names = ["cilium-values-management.yaml", "cilium-values-management-bootstrap.yaml"]
    elif TERRAFORM_ENV == "dev":
        names = ["cilium-values.yaml", "cilium-cluster-dev.yaml"]
        if include_clustermesh:
            names.append("clustermesh-management-peer.yaml")
        if include_bootstrap:
            names.append(bootstrap_file)
    elif TERRAFORM_ENV == "prod":
        names = ["cilium-values.yaml", "cilium-cluster-prod.yaml"]
        if include_clustermesh:
            names.append("clustermesh-management-peer.yaml")
        if include_bootstrap:
            names.append(bootstrap_file)
    else:
        names = []
    return [p for name in names if os.path.isfile(p := os.path.join(cilium_dir, name))]


def install_cilium_via_helm():
    """Cài Cilium trước mọi workload cần ClusterIP/DNS.

    Dev/prod dùng 2-step install để tránh deadlock trên multi-node cluster:
    - Step 1: kubeProxyReplacement: false (override trong bootstrap file) → Cilium KHÔNG attach
      tc BPF vào ens5 → API server vẫn accessible trong khi pods init.
    - Step 2: upgrade với kubeProxyReplacement: true (giá trị trong cilium-values.yaml) → kube-proxy
      replacement bật sau khi Cilium đã stable.
    """
    print("--- Step 0: Installing Cilium (kube-proxy replacement via Helm) ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    cilium_dir = os.path.join(_SCRIPT_DIR, "cilium")

    # For spoke clusters (dev/prod), use two-step bootstrap to avoid API blackout during init.
    # Management is single-node: API queries go via localhost, no tc-BPF deadlock.
    two_step = TERRAFORM_ENV in ("dev", "prod")

    # Step 1 bootstrap: no ClusterMesh (avoids hub-connection attempts during init).
    value_files = _build_cilium_value_files(cilium_dir, include_bootstrap=True, include_clustermesh=False)
    if not value_files:
        print(f"  ✗ Không tìm thấy file values Cilium trong {cilium_dir}")
        sys.exit(1)

    run_command("helm repo add cilium https://helm.cilium.io/", env=env)
    run_command("helm repo update cilium", env=env)

    if two_step:
        # Delete stale CiliumNode CRD objects before install.
        #
        # Root cause of API blackout on spoke clusters: when Cilium was previously installed
        # with the default IPAM pool (10.0.0.0/8), the operator allocated pod CIDRs like
        # 10.0.1.0/24 for one of the worker nodes. `helm uninstall` does NOT delete CRDs or
        # their objects, so these CiliumNode objects persist in etcd across installs and
        # reboots. On restart, the Cilium agent reads the stale CiliumNode spec and
        # immediately installs the route `10.0.1.0/24 via <worker> dev cilium_vxlan`. This
        # shadows the VPC peering route `10.0.0.0/16 via ens5`, so reply packets to the
        # OpenVPN server (10.0.1.152) go into the VXLAN tunnel and are dropped — API timeout.
        #
        # Fix: delete all CiliumNode objects so the operator allocates fresh /24 CIDRs from
        # the new pool (172.16.0.0/12, configured in cilium-values.yaml), which has no
        # overlap with any VPC or VPN subnet.
        print("  Pre-install: xóa CiliumNode objects cũ (stale pod CIDRs → VXLAN route conflict)...")
        subprocess.run(
            "kubectl delete ciliumnode --all --ignore-not-found",
            shell=True, env=env, check=False,
        )
        subprocess.run(
            "kubectl delete ciliumippool --all --ignore-not-found",
            shell=True, env=env, check=False,
        )
        print("  ✓ CiliumNode objects cleared — operator sẽ tự cấp phát CIDR mới từ 172.16.0.0/12")

    helm_wait_all = os.environ.get("CILIUM_HELM_WAIT", "").lower() in ("1", "true", "yes")
    helm_timeout = os.environ.get("CILIUM_HELM_TIMEOUT", _DEFAULT_CILIUM_HELM_TIMEOUT)

    def _helm_apply(vfiles: list[str], label: str) -> None:
        vf_args = " ".join(f"-f {shlex.quote(p)}" for p in vfiles)
        base = (
            "helm upgrade --install cilium cilium/cilium "
            f"--version {CILIUM_CHART_VERSION} "
            "--namespace kube-system "
            f"{vf_args} "
        )
        if helm_wait_all:
            print(
                f"  [{label}] Helm --wait (timeout {helm_timeout}) — "
                "bỏ CILIUM_HELM_WAIT để chỉ chờ dataplane."
            )
            run_command(f"{base}--wait --timeout {helm_timeout}", env=env)
        else:
            print(
                f"  [{label}] Helm apply không --wait — chờ dataplane sau. "
                "Muốn hành vi cũ: CILIUM_HELM_WAIT=1."
            )
            run_command(f"{base}--timeout {_CILIUM_HELM_APPLY_TIMEOUT}", env=env)

    if two_step:
        print(
            "  Spoke cluster (multi-node): dùng 2-step bootstrap.\n"
            "  Step 1: kubeProxyReplacement=false → Cilium khởi động mà không block port 6443.\n"
            "  Step 2: upgrade lên kubeProxyReplacement=true sau khi pods Ready."
        )
        _helm_apply(value_files, "Step 1/2 – CNI only, kubeProxyReplacement=false")
        print("  Chờ dataplane step 1 (CNI only)...")
        _wait_cilium_agent(env)
        _wait_cilium_operator(env)
        print("  ✓ Step 1 xong — nâng lên kubeProxyReplacement=true...")

        value_files_final = _build_cilium_value_files(cilium_dir, include_bootstrap=False)
        _helm_apply(value_files_final, "Step 2/2 – kubeProxyReplacement=true")
    else:
        _helm_apply(value_files, "install")

    # Datapath + operator: đủ cho Service VIP / CSI; Hubble UI & clustermesh-apiserver có thể vẫn Starting.
    print("  Chờ dataplane (DaemonSet cilium + Deployment cilium-operator)...")
    _wait_cilium_agent(env)
    _wait_cilium_operator(env)
    _kubectl_rollout_if_exists("daemonset/cilium-envoy", "kube-system", "20m", env)

    print("  ✓ Cilium dataplane sẵn sàng (RKE2 không kube-proxy). Kiểm tra thêm: kubectl get pods -n kube-system -l app.kubernetes.io/part-of=cilium")


def install_ebs_csi_driver():
    """Installs AWS EBS CSI Driver."""
    print("--- Step 1: Installing AWS EBS CSI Driver ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # --validate=false: tránh kubectl tải /openapi/v2 (payload lớn) — hay timeout qua VPN dù get nodes vẫn OK.
    run_command(
        "kubectl create serviceaccount ebs-csi-controller-sa -n kube-system --dry-run=client -o yaml | "
        "kubectl apply --validate=false --request-timeout=120s -f -",
        env=env,
    )
    run_command("helm repo add aws-ebs-csi-driver https://kubernetes-sigs.github.io/aws-ebs-csi-driver", env=env)
    run_command("helm repo update aws-ebs-csi-driver", env=env)
    run_command(
        "helm upgrade --install aws-ebs-csi-driver aws-ebs-csi-driver/aws-ebs-csi-driver "
        "--namespace kube-system --create-namespace "
        "--set controller.serviceAccount.create=false "
        "--set controller.serviceAccount.name=ebs-csi-controller-sa "
        "--timeout 10m",
        env=env,
    )
    print("  ✓ EBS CSI Driver installed.")


def _transfer_helm_ownership(env, namespace="argocd"):
    """Delete kubectl-managed ConfigMaps before Helm upgrade so Helm can recreate them.
    Fixes: 'conflict with kubectl-client-side-apply' on argocd-rbac-cm / argocd-cm.
    These ConfigMaps are re-applied by apply_argocd_projects_and_rbac() afterwards."""
    for cm in ["argocd-rbac-cm", "argocd-cm", "argocd-ssh-known-hosts-cm"]:
        res = subprocess.run(
            f"kubectl delete configmap {cm} -n {namespace} --ignore-not-found",
            shell=True, env=env, capture_output=True,
        )
        if res.returncode == 0:
            print(f"  ✓ Removed {cm} (Helm will recreate cleanly)")


def install_argocd():
    """Installs ArgoCD for GitOps deployments (management only)."""
    print("--- Step 2: Installing ArgoCD ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    run_command("helm repo add argo https://argoproj.github.io/argo-helm", env=env)
    subprocess.run("helm repo update argo", shell=True, env=env, capture_output=True)

    # Delete kubectl-managed ConfigMaps to avoid field-manager conflict on upgrade
    _transfer_helm_ownership(env)

    argocd_values_path = os.path.abspath(os.path.join(_SCRIPT_DIR, "argocd/bootstrap/01-argocd-install.yaml"))
    values_arg = ""
    if os.path.isfile(argocd_values_path):
        values_arg = f"--values {argocd_values_path} "
    else:
        print(f"  ⚠ Không có {argocd_values_path} — Helm Argo CD dùng default chart values.")
    run_command(
        f"helm upgrade --install argocd argo/argo-cd "
        f"--namespace argocd --create-namespace "
        f"{values_arg}"
        f"--timeout 10m",
        env=env,
    )
    print("  ✓ ArgoCD installed.")


def wait_for_argocd_ready():
    """Waits for ArgoCD server to be ready."""
    print("  Waiting for ArgoCD server...")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    waited = 0
    while waited < 300:
        try:
            result = subprocess.run(
                "kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server "
                "-o jsonpath='{.items[*].status.containerStatuses[0].ready}'",
                shell=True, env=env, capture_output=True, text=True, timeout=10,
            )
            if "true" in (result.stdout or ""):
                print(f"  ✓ ArgoCD ready (waited {waited}s)")
                return True
        except Exception:
            pass
        time.sleep(10)
        waited += 10
    print("  ⚠ ArgoCD not ready after 300s, proceeding anyway")
    return False


def apply_argocd_projects_and_rbac():
    """Apply ArgoCD Projects and RBAC configuration."""
    print("--- Step 3: Applying ArgoCD Projects and RBAC ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    if _apply_argocd_projects_manifests(env):
        print("  ✓ Argo CD Projects applied (helm template argocd/projects | kubectl apply)")
    if _apply_argocd_rbac_manifests(env):
        print("  ✓ Argo CD RBAC applied")


def install_external_secrets_operator():
    """Installs External Secrets Operator."""
    print("--- Step 2: Installing External Secrets Operator ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    res = subprocess.run(
        "kubectl get namespace external-secrets --request-timeout=5s 2>/dev/null && "
        "kubectl get deploy -n external-secrets external-secrets -o name 2>/dev/null",
        shell=True, env=env, capture_output=True, text=True, timeout=10,
    )
    if res.returncode == 0 and "external-secrets" in (res.stdout or ""):
        print("  ✓ External Secrets Operator already installed.")
        return
    run_command("helm repo add external-secrets https://charts.external-secrets.io", env=env, timeout=30)
    run_command("helm repo update external-secrets", env=env, timeout=60)
    run_command(
        "helm upgrade --install external-secrets external-secrets/external-secrets "
        "-n external-secrets --create-namespace --set installCRDs=true --timeout 5m",
        env=env, timeout=360,
    )
    print("  ✓ External Secrets Operator installed.")
    # Wait for ESO CRDs to be Established so ClusterSecretStore/ExternalSecret apply succeeds (ESO 2.x uses v1 API)
    for crd_name in ("clustersecretstores.external-secrets.io", "externalsecrets.external-secrets.io"):
        res = subprocess.run(
            f"kubectl wait --for=condition=Established crd/{crd_name} --timeout=120s 2>/dev/null",
            shell=True, env=env, capture_output=True, timeout=130,
        )
        if res.returncode == 0:
            print(f"  ✓ CRD {crd_name} established.")
        else:
            print(f"  ⚠ CRD {crd_name} wait failed (continuing anyway).")


def ensure_aws_secrets_credentials():
    """Tạo K8s Secret aws-credentials cho ESO (ClusterSecretStore auth)."""
    print("--- Step 3: AWS credentials for External Secrets ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    secret_name = "aws-credentials"  # phải khớp ClusterSecretStore (cluster-secret-store.yaml)

    # Ensure namespace exists (idempotent)
    run_command(
        "kubectl create namespace external-secrets --dry-run=client -o yaml | "
        "kubectl apply --validate=false --request-timeout=120s -f -",
        env=env,
        timeout=30,
    )

    res = subprocess.run(
        f"kubectl get secret {secret_name} -n external-secrets --request-timeout=5s 2>/dev/null",
        shell=True, env=env, capture_output=True, timeout=10,
    )
    if res.returncode == 0:
        print(f"  ✓ Secret {secret_name} already exists.")
        return
    access = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_val = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if not access or not secret_val:
        out_ak = subprocess.run(
            ["terraform", f"-chdir=environments/{TERRAFORM_ENV}", "output", "-raw", "eso_access_key_id"],
            cwd=TERRAFORM_DIR, capture_output=True, text=True, timeout=15,
        )
        out_sk = subprocess.run(
            ["terraform", f"-chdir=environments/{TERRAFORM_ENV}", "output", "-raw", "eso_secret_access_key"],
            cwd=TERRAFORM_DIR, capture_output=True, text=True, timeout=15,
        )
        if out_ak.returncode == 0 and out_sk.returncode == 0:
            access = out_ak.stdout.strip()
            secret_val = out_sk.stdout.strip()
        else:
            # Make failures visible (terraform not init / outputs missing / wrong env)
            ak_err = (out_ak.stderr or "").strip()
            sk_err = (out_sk.stderr or "").strip()
            if ak_err:
                print(f"  ✗ terraform output eso_access_key_id failed: {ak_err[:200]}")
            if sk_err:
                print(f"  ✗ terraform output eso_secret_access_key failed: {sk_err[:200]}")
    if access and secret_val:
        # ClusterSecretStore cần: access-key-id, secret-access-key
        yaml_out = subprocess.run(
            ["kubectl", "create", "secret", "generic", secret_name,
             "-n", "external-secrets",
             "--from-literal=access-key-id=" + access,
             "--from-literal=secret-access-key=" + secret_val,
             "--dry-run=client", "-o", "yaml"],
            env=env, capture_output=True, text=True, timeout=15,
        )
        if yaml_out.returncode != 0:
            err = (yaml_out.stderr or yaml_out.stdout or "").strip()
            print(f"  ✗ Failed to render secret manifest via kubectl. kubeconfig={kubeconfig_path}")
            print(f"    {err[:400]}")
            sys.exit(1)

        apply_out = subprocess.run(
            ["kubectl", "apply", "--validate=false", "--request-timeout=120s", "-f", "-"],
            input=yaml_out.stdout, env=env, capture_output=True, text=True, timeout=30,
        )
        if apply_out.returncode != 0:
            err = (apply_out.stderr or apply_out.stdout or "").strip()
            print(f"  ✗ Failed to apply secret {secret_name}. kubeconfig={kubeconfig_path}")
            print(f"    {err[:400]}")
            sys.exit(1)
        print(f"  ✓ Created {secret_name} in namespace external-secrets.")
    else:
        print("  ⚠ Credentials not found. Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY.")


def apply_external_secrets_manifests():
    """Apply ClusterSecretStore + ExternalSecret for current env.

    We render from Helm chart external-secrets/applications using config/base + config/env.
    This avoids relying on argocd/externalsecrets/ which may not exist.
    """
    print("--- Step 4: Applying External Secrets Manifests ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    # Wait for ESO webhook deployment to be Available (pods Ready) — prod có thể chậm hơn dev
    webhook_timeout = 240
    print(f"  Waiting for ESO webhook to be ready (up to {webhook_timeout}s)...")
    r = subprocess.run(
        "kubectl wait --for=condition=Available deployment/external-secrets-webhook "
        "-n external-secrets --timeout=%ds 2>/dev/null" % webhook_timeout,
        shell=True, env=env, capture_output=True, text=True, timeout=webhook_timeout + 15,
    )
    if r.returncode != 0:
        # Fallback: wait for Service to have endpoints (legacy check)
        for waited in range(0, webhook_timeout, 5):
            r2 = subprocess.run(
                "kubectl get endpoints external-secrets-webhook -n external-secrets "
                "-o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null",
                shell=True, env=env, capture_output=True, text=True, timeout=10,
            )
            if r2.returncode == 0 and (r2.stdout or "").strip():
                break
            if waited % 30 == 0 and waited > 0:
                print(f"  Waiting for ESO webhook endpoints... ({waited}s)")
            time.sleep(5)

    # Create namespaces first (ExternalSecret targets live here)
    for ns in ("meo-stationery", "database", "external-secrets"):
        subprocess.run(
            f"kubectl create namespace {ns} --dry-run=client -o yaml | "
            f"kubectl apply --validate=false --request-timeout=60s -f -",
            shell=True, env=env, timeout=30, capture_output=True,
        )

    chart_dir = os.path.join(_SCRIPT_DIR, "external-secrets", "applications")
    values_chart = os.path.join(chart_dir, "values.yaml")
    values_config_base = os.path.join(_SCRIPT_DIR, "config", "base", "config.yaml")
    values_config_env = os.path.join(_SCRIPT_DIR, "config", "env", f"{TERRAFORM_ENV}.yaml")
    if not os.path.isdir(chart_dir) or not os.path.isfile(values_chart):
        print(f"  ⚠ Helm chart not found for env={TERRAFORM_ENV}. Skipping apply.")
        print(f"    Expected: {chart_dir}/values.yaml")
        return
    if not os.path.isfile(values_config_base) or not os.path.isfile(values_config_env):
        print(f"  ⚠ Thiếu config merge: {values_config_base} hoặc {values_config_env}. Skipping apply.")
        return

    cmd = (
        f"helm template external-secrets {chart_dir} "
        f"-f {values_chart} -f {values_config_base} -f {values_config_env} | "
        "kubectl apply --validate=false --request-timeout=120s -f -"
    )

    # Apply with retry: webhook may be Ready but endpoints not yet routable
    for attempt in range(1, 4):
        apply_result = subprocess.run(
            cmd, shell=True, env=env, capture_output=True, text=True, timeout=120,
        )
        if apply_result.returncode == 0:
            print("  ✓ External Secrets manifests applied (from external-secrets/applications Helm chart).")
            return
        stderr = (apply_result.stderr or "")
        if "no endpoints available for service \"external-secrets-webhook\"" not in stderr:
            print(stderr or apply_result.stdout or "")
            sys.exit(1)
        if attempt < 3:
            print(f"  Webhook chưa sẵn sàng, retry sau 20s (lần {attempt}/3)...")
            time.sleep(20)
    print("  ✗ Apply External Secrets thất bại sau 3 lần (webhook vẫn không có endpoint).")
    sys.exit(1)


def deploy_argocd_applications():
    """Deploys ArgoCD Bootstrap Applications (sorted files under argocd/bootstrap/)."""
    print("--- Step 3: Deploying ArgoCD Bootstrap ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    wait_for_argocd_ready()
    time.sleep(10)
    _apply_argocd_projects_manifests(env)
    _apply_argocd_rbac_manifests(env)
    bootstrap_dir = os.path.join(_SCRIPT_DIR, "argocd", "bootstrap")
    root_app = os.path.join(bootstrap_dir, "02-root-app.yaml")
    if os.path.isfile(root_app):
        run_command(f"kubectl apply -f {root_app}", env=env, timeout=30)
        print("  ✓ Root App bootstrap applied.")
    else:
        manifests = sorted(glob.glob(os.path.join(bootstrap_dir, "*.yaml")))
        if not manifests:
            print(f"  ✗ Không có manifest trong {bootstrap_dir}")
            sys.exit(1)
        for path in manifests:
            run_command(f"kubectl apply -f {path}", env=env, timeout=60)
        print(f"  ✓ ArgoCD Bootstrap applied ({len(manifests)} file(s) trong bootstrap/).")
    print("  📌 Kiểm tra Applications trên Argo CD UI sau khi cluster dev/prod đã đăng ký.")


def resolve_dns_to_ip(dns_name, max_wait=60):
    for waited in range(0, max_wait, 5):
        try:
            ip = socket.gethostbyname(dns_name)
            print(f"  ✓ Resolved {dns_name} → {ip}")
            return ip
        except Exception:
            time.sleep(5)
    print(f"  ⚠ Failed to resolve {dns_name}")
    return None


def _write_setup_hosts_script(nlb_ip, hostnames):
    scripts_dir = os.path.join(_SCRIPT_DIR, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    script_path = os.path.join(scripts_dir, "setup-hosts.sh")
    hosts_str = " ".join(hostnames)
    sed_pattern = "|".join(h.replace(".", "\\.") for h in hostnames)
    content = f"""#!/usr/bin/env bash\nset -e\nENTRY="{nlb_ip}\\t{hosts_str}"\nsudo sed -i.bak -E '/{sed_pattern}/d' /etc/hosts\necho "$ENTRY" | sudo tee -a /etc/hosts\necho "Done: {hosts_str}"\n"""
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    print(f"  ⚠ Run to update /etc/hosts: sudo bash {script_path}")


def update_etc_hosts_for_nlb(nlb_dns):
    """Cập nhật /etc/hosts với DNS của web NLB (Terraform output web_nlb_dns_name) cho env hiện tại."""
    if not nlb_dns:
        return False
    hostnames = list(HOSTNAMES_FOR_NLB_BY_ENV.get(TERRAFORM_ENV, ()))
    if not hostnames:
        return False
    ip = resolve_dns_to_ip(nlb_dns)
    if not ip:
        return False
    try:
        result = subprocess.run(f"sudo cat /etc/hosts", shell=True, capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        new_lines = []
        for line in lines:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                new_lines.append(line)
                continue
            parts = line_strip.split()
            if len(parts) < 2:
                new_lines.append(line)
                continue
            kept_hosts = [h for h in parts[1:] if h not in hostnames]
            if len(kept_hosts) == 0:
                continue
            elif len(kept_hosts) < len(parts) - 1:
                new_lines.append(f"{parts[0]}\t{' '.join(kept_hosts)}")
            else:
                new_lines.append(line)
        new_lines.append(f"{ip}\t{' '.join(hostnames)}")
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("\n".join(new_lines) + "\n")
            tmp_path = tmp.name
        subprocess.check_call(f"sudo cp {tmp_path} /etc/hosts && sudo chmod 644 /etc/hosts", shell=True)
        os.unlink(tmp_path)
        print(f"  ✓ /etc/hosts updated: {ip} → {' '.join(hostnames)}")
        return True
    except Exception:
        _write_setup_hosts_script(ip, hostnames)
        return False


# ── Entry Point ───────────────────────────────────────────────────────────────
def auto_register_cluster_and_sync_git(env):
    """Tự động đăng ký cluster với ArgoCD và push manifest lên Git."""
    print(f"\n--- Step 5: Auto-registering {env} cluster & Syncing Git ---")
    
    # 1. Chạy script đăng ký cluster (script này đã được update để sửa cả file YAML)
    script_path = os.path.join(_SCRIPT_DIR, "scripts", "create-argocd-cluster-secrets.sh")
    if os.path.isfile(script_path):
        run_command(f"bash {script_path} {env}")
    else:
        print(f"  ⚠ Không tìm thấy {script_path}, bỏ qua bước đăng ký.")
        return

    # 2. Git commit & push các thay đổi trong thư mục argocd/clusters
    print(f"  Syncing cluster manifests to Git...")
    cluster_yaml = os.path.join(_SCRIPT_DIR, "argocd", "clusters", f"cluster-{env}.yaml")
    if os.path.isfile(cluster_yaml):
        try:
            # Kiểm tra xem có thay đổi không trước khi commit
            res = subprocess.run("git status --porcelain argocd/clusters/", shell=True, capture_output=True, text=True)
            if res.stdout.strip():
                run_command(f"git add {cluster_yaml}")
                # Dùng || true để tránh crash nếu không có gì thay đổi thực sự (dù status báo có)
                subprocess.run(f'git commit -m "chore: auto-update {env} cluster ip"', shell=True)
                run_command("git push")
                print(f"  ✓ Successfully pushed {env} cluster manifest to Git.")
            else:
                print("  ✓ Manifest is already up to date in Git.")
        except Exception as e:
            print(f"  ⚠ Lỗi khi Git Sync: {e}")
            print("  Hãy tự thực hiện 'git push' để ArgoCD nhận IP mới.")


def fix_ingress_nginx_webhook(env):
    """Xóa validating webhook ingress-nginx trên cluster env để Ingress apply được (tránh lỗi cert)."""
    script = os.path.join(_SCRIPT_DIR, "scripts", "fix-ingress-nginx-webhook.sh")
    if not os.path.isfile(script):
        return
    print(f"\n--- Step 5b: Fix ingress-nginx webhook on {env} (để Ingress apply được) ---")
    r = subprocess.run(["bash", script, env], cwd=_SCRIPT_DIR, capture_output=True, text=True, timeout=30)
    if r.stdout:
        print(r.stdout.strip())
    if r.returncode != 0 and r.stderr:
        print(f"  ⚠ {r.stderr.strip()[:200]}")


def trigger_argocd_app_sync(app_names, mgmt_kubeconfig):
    """Gọi refresh/sync cho các app ArgoCD (nếu có argocd CLI hoặc kubectl)."""
    env = os.environ.copy()
    env["KUBECONFIG"] = mgmt_kubeconfig
    for name in app_names:
        # argocd app sync <name> (nếu cài)
        r = subprocess.run(
            ["argocd", "app", "sync", name, "--async"],
            cwd=_SCRIPT_DIR, env=env, capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            print(f"  ✓ ArgoCD sync triggered: {name}")
        # else bỏ qua (argocd CLI có thể chưa cài)


def _management_private_ip_from_terraform():
    """Private IP đầu tiên (worker rồi master) từ terraform output management."""
    mgmt_dir = os.path.join(TERRAFORM_DIR, "environments", "management")
    if not os.path.isdir(mgmt_dir):
        return None
    try:
        out = subprocess.check_output(
            "terraform -chdir=environments/management output -json",
            shell=True,
            cwd=TERRAFORM_DIR,
            timeout=15,
        )
        data = json.loads(out)
        worker_ips = data.get("worker_private_ips", {}).get("value", [])
        master_ips = data.get("master_private_ip", {}).get("value", [])
        return (worker_ips or master_ips or [None])[0]
    except Exception:
        return None


def _patch_clustermesh_peer_management_ip():
    """
    Thay PLACEHOLDER_MGMT_PRIVATE_IP (terraform management) trong:
    - cilium/clustermesh-management-peer.yaml (ClusterMesh spoke→hub :32379)
    - app/be.yaml (Rollouts analysis Prometheus :32090 trên management)
    """
    placeholder = "PLACEHOLDER_MGMT_PRIVATE_IP"
    mgmt_dir = os.path.join(TERRAFORM_DIR, "environments", "management")
    if not os.path.isdir(mgmt_dir):
        print("  ⚠ Bỏ qua patch PLACEHOLDER_MGMT_PRIVATE_IP — không có terraform/environments/management.")
        return
    mgmt_ip = _management_private_ip_from_terraform()
    if not mgmt_ip:
        print("  ⚠ Không lấy được IP management (terraform worker_private_ips / master_private_ip) — bỏ qua patch placeholder.")
        return

    targets = [
        os.path.join(_SCRIPT_DIR, "cilium", "clustermesh-management-peer.yaml"),
        os.path.join(_SCRIPT_DIR, "app", "be.yaml"),
    ]
    for path in targets:
        if not os.path.isfile(path):
            continue
        with open(path, "r") as f:
            content = f.read()
        if placeholder not in content:
            continue
        with open(path, "w") as f:
            f.write(content.replace(placeholder, mgmt_ip))
        rel = os.path.relpath(path, _SCRIPT_DIR)
        print(f"  ✓ Patched {rel}: {placeholder} → {mgmt_ip}")


def patch_clustermesh_management_config():
    """
    Lấy private IP của master/worker node từ dev + prod terraform output,
    patch cilium-values-management.yaml để management ClusterMesh
    trỏ đúng vào AWS EC2 IP (thay PLACEHOLDER).
    Cuối cùng patch clustermesh-management-peer.yaml (spoke trỏ về hub).

    Nếu chưa provision dev/prod: dùng tạm 192.0.2.1 / 192.0.2.2 (RFC 5737 TEST-NET-1) —
    Kubernetes từ chối hostAliases nếu để nguyên chuỗi PLACEHOLDER_*.
    Sau khi có cluster dev/prod: git checkout -- cilium/cilium-values-management.yaml rồi chạy lại configure,
    hoặc sửa tay IP trong clustermesh.config.clusters.
    """
    values_file = os.path.join(_SCRIPT_DIR, "cilium", "cilium-values-management.yaml")
    if not os.path.isfile(values_file):
        return

    print("--- Step 1.5: Patching ClusterMesh management config ---")
    with open(values_file, "r") as f:
        content = f.read()

    # TEST-NET-1 (RFC 5737): định dạng IP hợp lệ, không dùng cho spoke thật — chỉ để Helm/Cilium khởi tạo khi chưa có terraform dev/prod.
    mesh_fallback = {"dev": "192.0.2.1", "prod": "192.0.2.2"}

    for env_name, placeholder, node_port in [
        ("dev", "PLACEHOLDER_DEV_NODE_IP", "32379"),
        ("prod", "PLACEHOLDER_PROD_NODE_IP", "32380"),
    ]:
        node_ip = None
        tf_env_dir = os.path.join(TERRAFORM_DIR, "environments", env_name)
        if os.path.isdir(tf_env_dir):
            try:
                out = subprocess.check_output(
                    f"terraform -chdir=environments/{env_name} output -json",
                    shell=True,
                    cwd=TERRAFORM_DIR,
                    timeout=15,
                )
                data = json.loads(out)
                worker_ips = data.get("worker_private_ips", {}).get("value", [])
                master_ips = data.get("master_private_ip", {}).get("value", [])
                node_ip = (worker_ips or master_ips or [None])[0]
            except Exception:
                pass

        if not node_ip:
            node_ip = mesh_fallback[env_name]
            print(
                f"  ⚠ {env_name}: chưa có IP từ terraform — dùng tạm {node_ip} (TEST-NET) cho hub ClusterMesh. "
                f"Sau khi provision {env_name}, git checkout -- cilium/cilium-values-management.yaml rồi chạy lại configure để IP thật."
            )

        if placeholder in content:
            content = content.replace(placeholder, node_ip)
            print(f"  ✓ Patched ClusterMesh {env_name}: {placeholder} → {node_ip}:{node_port}")
        elif node_ip not in mesh_fallback.values():
            # Đã patch trước đó (vd. TEST-NET) — thay bằng IP terraform mới
            old_fb = mesh_fallback[env_name]
            if old_fb in content and node_ip != old_fb:
                content = content.replace(old_fb, node_ip, 1)
                print(f"  ✓ Cập nhật ClusterMesh {env_name}: {old_fb} → {node_ip}:{node_port}")

    with open(values_file, "w") as f:
        f.write(content)

    _patch_clustermesh_peer_management_ip()


def main():
    print("\n" + "=" * 60)
    print(f"  CONFIGURE — Phase 2 (VPN Required) — env: {TERRAFORM_ENV}")
    print("  ⚠️  VPN phải đang bật: sudo openvpn --config minhtri.ovpn")
    print("=" * 60)

    # Guard: check VPN first
    check_vpn_connectivity()

    tf_out = get_terraform_output()
    wait_for_nlb_health_checks()

    if TERRAFORM_ENV == "management":
        patch_clustermesh_management_config()
    else:
        _patch_clustermesh_peer_management_ip()

    _patch_cilium_k8s_service_host(tf_out)
    install_cilium_via_helm()
    install_ebs_csi_driver()

    if TERRAFORM_ENV == "management":
        install_argocd()
        wait_for_argocd_ready()
        apply_argocd_projects_and_rbac()
        deploy_argocd_applications()
        print("\n  ─── ArgoCD cluster registration ───")
        print("  Sau khi deploy dev + prod, chạy:")
        print("     bash scripts/create-argocd-cluster-secrets.sh")
        print("     bash scripts/deploy-argocd-bootstrap.sh")
    else:
        install_external_secrets_operator()
        ensure_aws_secrets_credentials()
        apply_external_secrets_manifests()
        # Tự động đăng ký cluster với ArgoCD (Management) và Sync Git
        auto_register_cluster_and_sync_git(TERRAFORM_ENV)
        # Xóa webhook ingress-nginx để Ingress apply được (dynamic, không bước tay)
        fix_ingress_nginx_webhook(TERRAFORM_ENV)
        if TERRAFORM_ENV == "prod":
            fix_ingress_nginx_webhook("dev")  # một lần chạy configure prod sửa luôn dev
            mgmt_kube = os.path.join(_SCRIPT_DIR, "kube_config_rke2_management.yaml")
            if os.path.isfile(mgmt_kube):
                trigger_argocd_app_sync(
                    ["dev-meostation-backend-app", "prod-meostation-backend-app"],
                    mgmt_kube,
                )

    print("\n--- Updating /etc/hosts for web NLB (Ingress / Gateway) ---")
    nlb_dns = tf_out.get("web_nlb_dns_name", {}).get("value", "")
    if nlb_dns:
        update_etc_hosts_for_nlb(nlb_dns)
    else:
        print("  ⚠ web_nlb_dns_name chưa có trong terraform output. Chạy ./scripts/update-hosts.sh sau.")

    print("\n" + "=" * 60)
    print("  ✅ CONFIGURE COMPLETE!")
    print("=" * 60)
    print(f"\n  📋 Cluster access (VPN required):")
    print(f"     export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"     kubectl get nodes")
    if TERRAFORM_ENV == "management":
        print(f"\n  🌐 ArgoCD UI (cloud — VPN bật, dùng kube_config_rke2_management.yaml trong repo):")
        print(f"     Cách an toàn (luôn đúng file repo):")
        print(f"       bash scripts/argocd-ui-forward.sh")
        print(f"       → https://localhost:8443  (admin + password từ secret argocd-initial-admin-secret)")
        print(f"     Hoặc tay: export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
        print(f"       rồi: kubectl config view --minify -o jsonpath='{{.clusters[0].cluster.server}}' ; echo")
        print(f"       → phải là https://<IP-private>:6443 (RKE2), không phải http://localhost:8080.")
        print(f"  🌐 ArgoCD qua NLB (khi đã Ingress + /etc/hosts): http://argocd.local")
    else:
        # NLB (terraform loadbalancers) chỉ listener TCP :80 → NodePort 32080; không có :443.
        print(f"\n  🌐 App (Gateway): http://meo-stationery-{TERRAFORM_ENV}.local/")
    print(f"\n  🔧 Update /etc/hosts: ./scripts/update-hosts.sh {TERRAFORM_ENV}")
    print("\n  ⚠️  Dùng http:// (port 80). HTTPS trên NLB chưa bật — đừng gõ https:// hoặc sẽ không kết nối được.")
    print("=" * 60)


if __name__ == "__main__":
    main()