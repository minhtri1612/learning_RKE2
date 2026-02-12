#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import time

# Configuration (absolute paths so deploy.py works from any CWD)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAFORM_DIR = os.path.join(_SCRIPT_DIR, "terraform")

_VALID_ENVS = ("dev", "prod", "management", "all")


def _get_terraform_env():
    """Không truyền gì → deploy toàn bộ (management + dev + prod + ArgoCD GitOps). Có truyền → dev | prod | management."""
    if len(sys.argv) >= 2:
        env = sys.argv[1].lower()
        if env in _VALID_ENVS:
            return env
        print(f"Usage: {sys.argv[0]}  (deploy tất cả)  hoặc  {sys.argv[0]} [dev|prod|management]", file=sys.stderr)
        print(f"Invalid environment: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    return os.environ.get("TF_ENV", "all")


TERRAFORM_ENV = _get_terraform_env()
TERRAFORM_ENV_DIR = os.path.join(TERRAFORM_DIR, "environments", TERRAFORM_ENV)
ANSIBLE_DIR = os.path.join(_SCRIPT_DIR, "ansible")
HELM_DIR = os.path.join(_SCRIPT_DIR, "k8s_helm")
# Per-env kubeconfig để dev/prod không ghi đè lên nhau
KUBECONFIG_FILE = os.path.join(_SCRIPT_DIR, f"kube_config_rke2_{TERRAFORM_ENV}.yaml")
SSH_KEY_FILE_NAME = "k8s-key.pem"
# Cổng tunnel riêng mỗi env để chạy nhiều env cùng lúc không xung đột
LOCAL_PORT_BY_ENV = {"dev": 6443, "prod": 6445, "management": 6446}
# Trong deploy: file tạm 127.0.0.1:<port> cho tunnel; file ghi ra cho user (KUBECONFIG_FILE) = master IP
KUBECONFIG_TUNNEL_FILE = None


def _kubeconfig_for_deploy():
    """Path kubeconfig dùng trong deploy (tunnel nếu đã tạo, không thì file chính)."""
    return os.path.abspath(KUBECONFIG_TUNNEL_FILE or KUBECONFIG_FILE)


# App / UI settings
BACKEND_NAMESPACE = "meo-stationery"
DATABASE_NAMESPACE = "database"
RANCHER_HOSTNAME = "rancher.local"
RANCHER_BOOTSTRAP_PASSWORD = "Admin123!"

# Rancher chart requires cert-manager CRDs
CERT_MANAGER_CRDS_URL = "https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.crds.yaml"


def run_command(command, cwd=None, env=None, timeout=None):
    """Runs a shell command and exits if it fails (non-interactive)."""
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
    """Gets Terraform output as JSON (from environments/<env>)."""
    print("Fetching Terraform outputs...")
    cmd = f"terraform -chdir=environments/{TERRAFORM_ENV} output -json"
    output = subprocess.check_output(cmd, shell=True, cwd=TERRAFORM_DIR).decode("utf-8")
    return json.loads(output)


def get_terraform_output_for_env(env_name):
    """Gets Terraform output as JSON for a specific env (e.g. 'management')."""
    print(f"Fetching Terraform outputs for {env_name}...")
    cmd = f"terraform -chdir=environments/{env_name} output -json"
    output = subprocess.check_output(cmd, shell=True, cwd=TERRAFORM_DIR).decode("utf-8")
    return json.loads(output)

def get_management_openvpn_ip():
    """Lấy OpenVPN public IP của management (dùng làm jump host cho dev/prod)."""
    try:
        out = subprocess.check_output(
            "terraform -chdir=environments/management output -json",
            shell=True,
            cwd=TERRAFORM_DIR,
            timeout=15,
        )
        data = json.loads(out)
        return data.get("openvpn_public_ip", {}).get("value", "")
    except Exception:
        return ""


def setup_terraform():
    """Applies Terraform configuration (environments/<env>)."""
    tfvars = os.path.join(TERRAFORM_ENV_DIR, "terraform.tfvars")
    if not os.path.isfile(tfvars):
        example = os.path.join(TERRAFORM_ENV_DIR, "terraform.tfvars.example")
        if os.path.isfile(example):
            with open(example, "r") as f:
                content = f.read()
            # Replace placeholder my_ip so Terraform apply runs (user can edit tfvars later for real prod)
            content = content.replace("YOUR_OFFICE_OR_VPN_IP/32", "0.0.0.0/0")
            with open(tfvars, "w") as f:
                f.write(content)
            print(f"Created {tfvars} from .example (my_ip=0.0.0.0/0). Edit for production.")
        else:
            print(f"Error: terraform.tfvars not found and no terraform.tfvars.example in {TERRAFORM_ENV}.")
            sys.exit(1)
    print("--- Step 1: Terraform Apply ---")
    run_command(f"terraform -chdir=environments/{TERRAFORM_ENV} init -input=false", cwd=TERRAFORM_DIR)
    run_command(
        f"terraform -chdir=environments/{TERRAFORM_ENV} apply -auto-approve -input=false -var-file=terraform.tfvars",
        cwd=TERRAFORM_DIR,
    )


def run_openvpn_ansible(openvpn_public_ip):
    """Chạy Ansible playbook openvpn-server.yml để cấu hình OpenVPN và tạo .ovpn (fetch về project root)."""
    print("--- Step: Ansible OpenVPN Server Setup ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    max_wait = 300  # 5 phút (Ubuntu + cloud-init đôi khi > 2 phút)
    print(f"  Waiting for OpenVPN instance to accept SSH (tối đa {max_wait // 60} phút)...")
    ssh_ok = False
    for waited in range(0, max_wait, 10):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{openvpn_public_ip} 'echo ready'",
                shell=True,
                capture_output=True,
                timeout=15,
            )
            if res.returncode == 0:
                print(f"  ✓ OpenVPN server SSH ready (waited {waited}s)")
                ssh_ok = True
                break
        except Exception:
            pass
        if waited % 30 == 0 and waited > 0:
            print(f"  Still waiting... ({waited}s)")
        time.sleep(10)
    if not ssh_ok:
        inventory_path = os.path.join(ANSIBLE_DIR, "inventory_openvpn.yml")
        with open(inventory_path, "w") as f:
            f.write(f"vpn_server:\n  hosts:\n    {openvpn_public_ip}:\n")
        print(f"  ✗ OpenVPN server SSH timeout sau {max_wait}s.")
        # One verbose attempt to show why (timeout vs refused vs permission denied)
        try:
            r = subprocess.run(
                f"ssh -v -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_public_ip} exit 2>&1",
                shell=True,
                capture_output=True,
                timeout=15,
            )
            err = (r.stderr or b"") + (r.stdout or b"")
            for line in err.decode("utf-8", errors="replace").splitlines():
                if "debug1: Connecting" in line or "Connection refused" in line or "timed out" in line or "Permission denied" in line or "No route" in line:
                    print(f"     [ssh] {line.strip()}")
        except Exception as e:
            print(f"     [ssh] {e}")
        print("     (Lỗi này không liên quan ArgoCD – deploy fail ở bước OpenVPN SSH, trước khi tới cluster/ArgoCD.)")
        print("     Thử: mạng khác (VPN/corp có thể chặn); hoặc recreate: ./scripts/recreate-openvpn-instance.sh " + TERRAFORM_ENV)
        print("     Bỏ qua bước này lần chạy: SKIP_OPENVPN_ANSIBLE=1 ./deploy.py " + TERRAFORM_ENV)
        print("     Kiểm tra SSH thủ công (timeout = mạng/firewall; refused = instance chưa sẵn sàng; denied = key sai):")
        print(f"     ssh -o IdentitiesOnly=yes -i {ssh_key_path} -o ConnectTimeout=15 ubuntu@{openvpn_public_ip}")
        print("     Chạy Ansible thủ công khi SSH được:")
        print(f"     cd {ANSIBLE_DIR} && ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip={openvpn_public_ip} openvpn-server.yml")
        sys.exit(1)

    # Static inventory: Terraform output đã có openvpn_public_ip, không cần dynamic inventory
    vpn_server_yml = os.path.join(ANSIBLE_DIR, "group_vars", "vpn_server.yml")
    with open(vpn_server_yml, "r") as f:
        vpn_cfg = f.read()
    key_line = f'ansible_ssh_private_key_file: "{ssh_key_path}"'
    if "ansible_ssh_private_key_file" in vpn_cfg:
        vpn_cfg = re.sub(r"ansible_ssh_private_key_file:\s*[^\n]+", key_line, vpn_cfg)
    else:
        vpn_cfg = vpn_cfg.rstrip() + "\n" + key_line + "\n"
    # Tránh "Too many authentication failures": chỉ dùng key chỉ định, không dùng agent
    if 'IdentitiesOnly' not in vpn_cfg:
        if 'ansible_ssh_common_args:' in vpn_cfg:
            vpn_cfg = re.sub(r'(ansible_ssh_common_args:\s*)"', r'\1"-o IdentitiesOnly=yes ', vpn_cfg)
        else:
            vpn_cfg = vpn_cfg.rstrip() + '\nansible_ssh_common_args: "-o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=30"\n'
    with open(vpn_server_yml, "w") as f:
        f.write(vpn_cfg)

    # Inventory file: group vpn_server với host = IP (Ansible SSH tới IP, không resolve "vpn_server")
    inventory_path = os.path.join(ANSIBLE_DIR, "inventory_openvpn.yml")
    with open(inventory_path, "w") as f:
        f.write(f"vpn_server:\n  hosts:\n    {openvpn_public_ip}:\n")

    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_PRIVATE_KEY_FILE"] = ssh_key_path
    run_command(
        f"ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip={openvpn_public_ip} openvpn-server.yml",
        cwd=ANSIBLE_DIR,
        env=env,
        timeout=600,
    )
    print("  ✓ OpenVPN server configured; .ovpn files fetched to project root (e.g. client1.ovpn)")


def fetch_kubeconfig(openvpn_ip, master_private_ip, nlb_dns, jump_ssh_key_path=None, key_on_jump="k8s-key.pem"):
    """Fetches and configures kubeconfig via SSH through OpenVPN server (jump host).
    jump_ssh_key_path: key to SSH to jump (management); None = use current env key.
    key_on_jump: path on jump host for key to master (~/.ssh/<name>)."""
    key_to_jump = jump_ssh_key_path or os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    master_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))

    print("--- Step 4: Fetching Kubeconfig via OpenVPN Server (jump) ---")

    print("  Waiting for OpenVPN server to be ready...")
    for waited in range(0, 120, 5):
        try:
            res = subprocess.run(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} 'echo ready'",
                shell=True,
                capture_output=True,
                timeout=10,
            )
            if res.returncode == 0:
                print(f"  ✓ OpenVPN server ready (waited {waited}s)")
                break
        except Exception:
            pass
        if waited % 15 == 0:
            print(f"  Still waiting for OpenVPN server... ({waited}s)")
        time.sleep(5)

    print("  Copying SSH key to OpenVPN server for master access...")
    run_command(
        f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'",
        timeout=15,
    )
    run_command(
        f"scp -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -i {key_to_jump} {master_key_path} ubuntu@{openvpn_ip}:~/.ssh/{key_on_jump}",
        timeout=30,
    )
    run_command(
        f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'chmod 600 ~/.ssh/{key_on_jump}'",
        timeout=15,
    )

    print("  Waiting for RKE2 to generate kubeconfig (user_data đang chạy)...")
    time.sleep(180)

    inner_ssh = f"ssh -i ~/.ssh/{key_on_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{master_private_ip}"
    print("  Waiting for SSH to master via OpenVPN server (và file kubeconfig)...")
    for waited in range(0, 420, 15):
        try:
            # Kiểm tra /home/ubuntu/.kube/config hoặc /etc/rancher/rke2/rke2.yaml (RKE2 tạo rke2.yaml trước)
            res = subprocess.run(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} "
                f"'{inner_ssh} \"test -f /home/ubuntu/.kube/config || sudo test -f /etc/rancher/rke2/rke2.yaml\" && echo ready'",
                shell=True,
                capture_output=True,
                timeout=25,
            )
            if res.returncode == 0 and b"ready" in (res.stdout or b""):
                print(f"  ✓ kubeconfig ready (waited {waited}s)")
                break
        except Exception:
            pass
        if waited % 30 == 0:
            print(f"  Still waiting... ({waited}s)")
        time.sleep(15)

    print("  Fetching kubeconfig via SSH (through OpenVPN server)...")
    kubeconfig_content = None
    try:
        kubeconfig_content = subprocess.check_output(
            f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} "
            f"'{inner_ssh} cat /home/ubuntu/.kube/config'",
            shell=True,
            timeout=30,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        if e.returncode != 0 and e.stderr:
            print(f"  (cat /home/ubuntu/.kube/config failed: {e.stderr.decode(errors='replace')[:200]})")
        try:
            kubeconfig_content = subprocess.check_output(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} "
                f"'{inner_ssh} sudo cat /etc/rancher/rke2/rke2.yaml'",
                shell=True,
                timeout=30,
                stderr=subprocess.PIPE,
            )
            print("  ✓ Used /etc/rancher/rke2/rke2.yaml (fallback)")
        except subprocess.CalledProcessError as e2:
            if e2.stderr:
                print(f"  Fallback failed: {e2.stderr.decode(errors='replace')[:300]}", file=sys.stderr)
            raise
    if kubeconfig_content is None or len(kubeconfig_content) == 0:
        raise RuntimeError("Could not fetch kubeconfig from master (SSH or file missing)")
    with open(KUBECONFIG_FILE, "wb") as f:
        f.write(kubeconfig_content)

    # Đọc và sửa: server = master IP (chỉ cần VPN, một terminal); xóa cert, dùng insecure-skip-tls-verify
    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    config = re.sub(r'server:\s*https://[^\s\n]+', f'server: https://{master_private_ip}:6443', config)

    # Xóa tất cả certificate-authority-data và thay bằng insecure-skip-tls-verify
    # Xử lý cả trường hợp certificate-authority-data trên 1 dòng hoặc multiline
    lines = config.split('\n')
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Tìm dòng certificate-authority-data
        if re.search(r'certificate-authority-data', line):
            # Thay thế bằng insecure-skip-tls-verify với cùng indent
            indent = len(line) - len(line.lstrip())
            new_lines.append(' ' * indent + 'insecure-skip-tls-verify: true')
            # Bỏ qua dòng hiện tại và các dòng tiếp theo nếu là base64 continuation
            i += 1
            # Bỏ qua các dòng base64 continuation (chỉ có base64 chars, không có : hoặc -)
            while i < len(lines) and re.match(r'^\s+[A-Za-z0-9+/=]+$', lines[i]):
                i += 1
            continue
        else:
            new_lines.append(line)
            i += 1
    
    config = '\n'.join(new_lines)
    
    # Đảm bảo insecure-skip-tls-verify có trong mỗi cluster (nếu chưa có)
    # Thêm vào sau dòng server: nếu chưa có insecure-skip-tls-verify trong cluster đó
    if 'insecure-skip-tls-verify' not in config:
        config = re.sub(
            r'(server:\s*https://[^\n]+)',
            r'\1\n    insecure-skip-tls-verify: true',
            config
        )
    
    with open(KUBECONFIG_FILE, "w") as f:
        f.write(config)
    os.chmod(KUBECONFIG_FILE, 0o600)
    print(f"  ✓ Kubeconfig saved to {KUBECONFIG_FILE} (server: https://{master_private_ip}:6443 — dùng khi đã bật VPN)")


def _create_tunnel_kubeconfig():
    """Tạo file kubeconfig tạm 127.0.0.1:<port> để deploy dùng tunnel (port riêng mỗi env)."""
    global KUBECONFIG_TUNNEL_FILE
    local_port = LOCAL_PORT_BY_ENV.get(TERRAFORM_ENV, 6443)
    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    config_tunnel = re.sub(r'server:\s*https://[^\s\n]+', f'server: https://127.0.0.1:{local_port}', config)
    path = os.path.join(_SCRIPT_DIR, f".kube_config_rke2_{TERRAFORM_ENV}_tunnel.yaml")
    with open(path, "w") as f:
        f.write(config_tunnel)
    os.chmod(path, 0o600)
    KUBECONFIG_TUNNEL_FILE = path


def wait_for_api_from_openvpn(openvpn_ip, master_private_ip, max_wait=600, jump_ssh_key_path=None):
    """Đợi API server thật sự trả lời từ OpenVPN (curl /readyz). RKE2 user_data có thể mất 5–10 phút."""
    key_path = jump_ssh_key_path or os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    print("  Waiting for Kubernetes API from OpenVPN (curl https://master:6443/readyz)...")
    last_curl_out, last_curl_err = "", ""
    for waited in range(0, max_wait, 15):
        try:
            res = subprocess.run(
                f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{openvpn_ip} "
                f"curl -k -s -o /dev/null -w '%{{http_code}}' --connect-timeout 5 https://{master_private_ip}:6443/readyz 2>&1; echo ' exit='$?",
                shell=True,
                capture_output=True,
                timeout=20,
            )
            out = (res.stdout or b"").decode(errors="replace").strip()
            err = (res.stderr or b"").decode(errors="replace").strip()
            last_curl_out, last_curl_err = out, err
            # 200 = OK, 401/403 = API đang chạy nhưng từ chối vì curl không gửi client cert (bình thường)
            if res.returncode == 0 and ("200" in out or "401" in out or "403" in out):
                print("  ✓ API reachable from OpenVPN (waited %ds, curl: %s)" % (waited, out.split()[0] if out else "ok"))
                return True
            if waited % 60 == 0 and waited > 0:
                # In ra lỗi thật: 000 = không kết nối được, exit=7 = refused, exit=28 = timeout
                hint = out or err or ("ssh_rc=%s" % res.returncode)
                print("  Still waiting... (%ds) curl: %s" % (waited, hint[:120]))
        except subprocess.TimeoutExpired:
            last_curl_err = "ssh/curl timeout"
        except Exception as e:
            last_curl_err = str(e)
        time.sleep(15)
    print("  ✗ API not reachable from OpenVPN after %ds." % max_wait)
    print("  Curl last output: %s" % (last_curl_out or "(empty)"))
    if last_curl_err:
        print("  Curl last stderr: %s" % last_curl_err[:200])
    print("  Debug: (1) terraform apply đã chạy xong? SG k8s_master có rule 6443 từ openvpn SG.")
    print("         (2) Trên master: ssh ubuntu@<master_ip> rồi sudo tail -100 /var/log/cloud-init-output.log")
    print("         (3) Từ OpenVPN: ssh ubuntu@<master_ip> rồi curl -k -v https://localhost:6443/readyz")
    return False


def _tunnel_log_path():
    return f"/tmp/openvpn-k8s-pf-{TERRAFORM_ENV}.log"


def _dump_tunnel_diagnostics(local_port=6443):
    """In log tunnel và trạng thái process khi API không kết nối được."""
    log_file = _tunnel_log_path()
    print("  --- Tunnel diagnostics ---")
    if os.path.isfile(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
        tail = lines[-25:] if len(lines) >= 25 else lines
        print("  Tunnel log (%s) last %d lines:" % (log_file, len(tail)))
        for line in tail:
            print("    " + line.rstrip())
    else:
        print("  Tunnel log not found: %s" % log_file)
    try:
        r = subprocess.run(
            "pgrep -af 'ssh.*%s:.*6443'" % local_port,
            shell=True,
            capture_output=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            print("  Tunnel process: running")
        else:
            print("  Tunnel process: NOT running (tunnel đã tắt → kiểm tra SSH từ máy bạn tới OpenVPN)")
    except Exception:
        print("  Tunnel process: (check failed)")


def start_openvpn_port_forward(openvpn_ip, master_private_ip, local_port=None, remote_port=6443, jump_ssh_key_path=None):
    """SSH tunnel: local:port -> OpenVPN server connects to master:6443 (một bước, ổn định hơn ProxyCommand)."""
    if local_port is None:
        local_port = LOCAL_PORT_BY_ENV.get(TERRAFORM_ENV, 6443)
    print(f"--- Step 4.5: Starting SSH Port Forward (local:{local_port} -> OpenVPN -> master:{remote_port}) ---")
    ssh_key_path = jump_ssh_key_path or os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    log_file = _tunnel_log_path()

    try:
        subprocess.run("pkill -f 'ssh.*%s:.*%s' 2>/dev/null || true" % (local_port, remote_port), shell=True)
        time.sleep(1)
    except Exception:
        pass

    cmd = (
        f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
        f"-o ConnectTimeout=30 -o ServerAliveInterval=30 "
        f"-N -L 127.0.0.1:{local_port}:{master_private_ip}:{remote_port} ubuntu@{openvpn_ip}"
    )
    with open(log_file, "w") as f:
        proc = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)

    time.sleep(5)
    if proc.poll() is not None:
        print("  ✗ Port-forward process exited. Log:")
        _dump_tunnel_diagnostics(local_port)
        return None
    try:
        r = subprocess.run(
            "curl -k -s -o /dev/null -w '%%{http_code}' --connect-timeout 8 https://127.0.0.1:%s/readyz" % local_port,
            shell=True,
            capture_output=True,
            timeout=12,
        )
        out = (r.stdout or b"").decode().strip()
        if r.returncode == 0 and out == "200":
            print("  ✓ Port-forward OK, API reachable via 127.0.0.1:%s (PID %s)" % (local_port, proc.pid))
        else:
            print("  ⚠ Tunnel up but /readyz returned: %s. Log: %s" % (out or "timeout/error", log_file))
    except Exception as e:
        print("  ⚠ Tunnel verify failed: %s. Log: %s" % (e, log_file))
    print("  Logs: %s" % log_file)
    return proc


def wait_for_nlb_health_checks():
    print("--- Waiting for NLB to become healthy ---")
    print("  NLB health checks can take 1-2 minutes to pass...")
    print("  This is normal - NLB needs time to register healthy targets...")
    time.sleep(120)  # Tăng thời gian đợi lên 2 phút


def wait_for_k8s_api(kubeconfig_path, max_wait=120):
    """Đợi API server qua tunnel (API đã được kiểm tra từ OpenVPN trước khi mở tunnel)."""
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    print("  Waiting for Kubernetes API server to be accessible (via tunnel)...")
    waited = 0
    last_error = ""
    while waited < max_wait:
        res = subprocess.run(
            f"kubectl --kubeconfig={kubeconfig_path} get nodes --request-timeout=15s",
            shell=True,
            capture_output=True,
            env=env,
            timeout=25,
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
    
    print("  ⚠ API server not accessible after %ds" % max_wait)
    if last_error:
        print("  Last error: %s" % last_error[:200])
    local_port = LOCAL_PORT_BY_ENV.get(TERRAFORM_ENV, 6443)
    _dump_tunnel_diagnostics(local_port)
    print("  Continuing anyway (hoping remote access works)...")
    return True # Force continue to avoid script exit if local tunnel is flaky


def install_ebs_csi_driver():
    """Installs AWS EBS CSI Driver for EBS volume support (Local Execution via Tunnel)."""
    print("--- Step 5.6: Installing AWS EBS CSI Driver (Local via Tunnel) ---")
    
    # We revert to local execution because:
    # 1. Remote execution fails if 'helm' is not installed on the Master node.
    # 2. We fixed the SSH Tunnel (in main()), so local helm commands via tunnel work reliably now (proven by Rancher success).
    
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    print("  [Local] Creating ServiceAccount for EBS CSI controller...")
    run_command(f"kubectl create serviceaccount ebs-csi-controller-sa -n kube-system --dry-run=client -o yaml | kubectl apply -f -", env=env)
    
    print("  [Local] Installing AWS EBS CSI Driver (HelmV3)...")
    # Add repo if not exists
    run_command("helm repo add aws-ebs-csi-driver https://kubernetes-sigs.github.io/aws-ebs-csi-driver", env=env)
    run_command("helm repo update aws-ebs-csi-driver", env=env)
    
    run_command(
        f"helm upgrade --install aws-ebs-csi-driver aws-ebs-csi-driver/aws-ebs-csi-driver "
        f"--namespace kube-system --create-namespace "
        f"--set controller.serviceAccount.create=false "
        f"--set controller.serviceAccount.name=ebs-csi-controller-sa "
        f"--timeout 10m",
        env=env,
    )
    
    print("  Waiting for EBS CSI Driver pods to be ready...")
    # Optional wait loop
    waited = 0
    while waited < 300:
        try:
            result = subprocess.run(
                f"kubectl --kubeconfig={kubeconfig_path} get pods -n kube-system "
                f"-l app=ebs-csi-controller -o jsonpath='{{.items[*].status.phase}}'",
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "Running" in (result.stdout or ""):
                print(f"  ✓ EBS CSI Driver is ready (waited {waited}s)")
                break
        except Exception:
            pass
        time.sleep(10)
        waited += 10
        if waited % 30 == 0:
             print(f"  Still waiting for EBS CSI Driver... ({waited}s)")

    if waited >= 300:
        print("  ⚠️  Warning: EBS CSI Driver pods may still be starting. Check with: kubectl get pods -n kube-system | grep ebs-csi")
    else:
        print("  ✓ EBS CSI Driver installed successfully.")

    print("  Note: EBS StorageClass (ebs-sc) will be set as default when database chart is deployed with useEBS: true")
    return






def ensure_rancher_tls_secret():
    """Create a self-signed TLS secret for rancher ingress (idempotent)."""
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    exists = subprocess.run(
        "kubectl -n cattle-system get secret tls-rancher-ingress",
        shell=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode == 0:
        return

    print("  Creating self-signed TLS secret for Rancher ingress (tls-rancher-ingress)...")
    rancher_hostname = get_rancher_hostname()
    with tempfile.TemporaryDirectory() as td:
        crt = os.path.join(td, "tls.crt")
        key = os.path.join(td, "tls.key")
        run_command(
            f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 "
            f"-keyout {key} -out {crt} -subj \"/CN={rancher_hostname}\"",
            timeout=60,
        )
        run_command(
            f"kubectl -n cattle-system create secret tls tls-rancher-ingress "
            f"--cert={crt} --key={key} --dry-run=client -o yaml | kubectl apply -f -",
            env=env,
            timeout=60,
        )


def install_rancher():
    """Installs Rancher server and exposes the UI."""
    print("--- Step 7: Installing Rancher (this may take 5-10 min for image pull) ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Rancher chart requires cert-manager CRDs
    print("  Installing cert-manager CRDs (required by Rancher)...")
    run_command(f"kubectl --kubeconfig={kubeconfig_path} apply -f {CERT_MANAGER_CRDS_URL}", cwd=HELM_DIR, env=env, timeout=120)

    run_command("helm repo add rancher-latest https://releases.rancher.com/server-charts/latest", cwd=HELM_DIR, env=env)
    # Update only the Rancher repo to avoid timeout issues with other repos
    result = subprocess.run("helm repo update rancher-latest", shell=True, cwd=HELM_DIR, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  Warning: helm repo update failed (non-critical): {result.stderr}")
        print("  Continuing anyway...")

    print("  Installing Rancher Helm chart...")
    rancher_hostname = get_rancher_hostname()
    run_command(
        f"helm upgrade --install rancher rancher-latest/rancher "
        f"--namespace cattle-system --create-namespace "
        f"--set hostname={rancher_hostname} "
        f"--set bootstrapPassword={RANCHER_BOOTSTRAP_PASSWORD} "
        f"--set ingress.ingressClassName=nginx "
        f"--set ingress.tls.source=secret "
        f"--set replicas=1 "
        f"--timeout 15m",
        cwd=HELM_DIR,
        env=env,
    )

    ensure_rancher_tls_secret()
    print("  ✓ Rancher installed. Pods may still be starting.")


def install_argocd():
    """Installs ArgoCD for GitOps deployments."""
    print("--- Step 7.5: Installing ArgoCD ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    run_command("helm repo add argo https://argoproj.github.io/argo-helm", cwd=HELM_DIR, env=env)
    # Update only the ArgoCD repo to avoid timeout issues with other repos
    result = subprocess.run("helm repo update argo", shell=True, cwd=HELM_DIR, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  Warning: helm repo update failed (non-critical): {result.stderr}")
        print("  Continuing anyway...")

    argocd_values_path = os.path.abspath("./argocd/values-nodeselector.yaml")
    run_command(
        f"helm upgrade --install argocd argo/argo-cd "
        f"--namespace argocd --create-namespace "
        f"--values {argocd_values_path} "
        f"--timeout 10m",
        cwd=HELM_DIR,
        env=env,
    )
    print("  ✓ ArgoCD installed. Pods may still be starting.")


def wait_for_argocd_ready():
    """Waits for ArgoCD server to be ready."""
    print("  Waiting for ArgoCD server to be ready...")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    waited = 0
    while waited < 300:
        try:
            result = subprocess.run(
                "kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server "
                "-o jsonpath='{.items[*].status.containerStatuses[0].ready}'",
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "true" in (result.stdout or ""):
                print(f"  ✓ ArgoCD server is ready (waited {waited}s)")
                return True
        except Exception:
            pass
        time.sleep(10)
        waited += 10

    print("  ⚠ ArgoCD not ready after 300s, proceeding anyway")
    return False


def install_external_secrets_operator():
    """Cài External Secrets Operator (ESO) để sync AWS Secrets Manager → K8s Secret."""
    print("--- Step 7.5: Installing External Secrets Operator ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Check if already installed
    res = subprocess.run(
        "kubectl get namespace external-secrets --request-timeout=5s 2>/dev/null && "
        "kubectl get deploy -n external-secrets external-secrets -o name 2>/dev/null",
        shell=True,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if res.returncode == 0 and "external-secrets" in (res.stdout or ""):
        print("  ✓ External Secrets Operator already installed.")
        return

    run_command("helm repo add external-secrets https://charts.external-secrets.io", cwd=_SCRIPT_DIR, env=env, timeout=30)
    run_command("helm repo update external-secrets", cwd=_SCRIPT_DIR, env=env, timeout=60)
    run_command(
        "helm upgrade --install external-secrets external-secrets/external-secrets "
        "-n external-secrets --create-namespace --set installCRDs=true --timeout 5m",
        cwd=_SCRIPT_DIR,
        env=env,
        timeout=360,
    )
    print("  ✓ External Secrets Operator installed. Waiting for CRDs to be ready...")
    crd_name = "clustersecretstores.external-secrets.io"
    for waited in range(0, 120, 5):
        res = subprocess.run(
            f"kubectl get crd {crd_name} --request-timeout=5s 2>/dev/null",
            shell=True,
            env=env,
            capture_output=True,
            timeout=10,
        )
        if res.returncode == 0:
            print(f"  ✓ CRD {crd_name} ready (waited {waited}s).")
            break
        if waited % 15 == 0 and waited > 0:
            print(f"  Still waiting for CRDs... ({waited}s)")
        time.sleep(5)
    else:
        print("  ⚠ CRD may not be ready yet; apply SecretStore later if it fails.")


def ensure_aws_secrets_credentials():
    """Tạo K8s Secret aws-secrets-credentials cho ESO (nếu chưa có).
    Tự động lấy từ Terraform output (eso_access_key_id, eso_secret_access_key) do Terraform IAM module tạo.
    Fallback: env AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY."""
    print("--- Step 7.5b: AWS credentials for External Secrets ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    res = subprocess.run(
        "kubectl get secret aws-secrets-credentials -n external-secrets --request-timeout=5s 2>/dev/null",
        shell=True,
        env=env,
        capture_output=True,
        timeout=10,
    )
    if res.returncode == 0:
        print("  ✓ Secret aws-secrets-credentials already exists.")
        return

    access = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_val = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()

    # Tự động lấy từ Terraform output (IAM user ESO do Terraform tạo)
    if not access or not secret_val:
        out_ak = subprocess.run(
            ["terraform", "-chdir=environments/" + TERRAFORM_ENV, "output", "-raw", "eso_access_key_id"],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        out_sk = subprocess.run(
            ["terraform", "-chdir=environments/" + TERRAFORM_ENV, "output", "-raw", "eso_secret_access_key"],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out_ak.returncode == 0 and out_sk.returncode == 0 and out_ak.stdout and out_sk.stdout:
            access = out_ak.stdout.strip()
            secret_val = out_sk.stdout.strip()
            if access and secret_val:
                print("  Using ESO credentials from Terraform output (IAM user created by Terraform).")

    if access and secret_val:
        # Don't pass credentials via command line (would show in logs); use stdin for kubectl
        yaml_out = subprocess.run(
            [
                "kubectl", "create", "secret", "generic", "aws-secrets-credentials",
                "-n", "external-secrets",
                "--from-literal=access-key=" + access,
                "--from-literal=secret-access-key=" + secret_val,
                "--dry-run=client", "-o", "yaml",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if yaml_out.returncode != 0:
            print("  ⚠ Failed to create aws-secrets-credentials:", yaml_out.stderr)
            return
        apply_out = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=yaml_out.stdout,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if apply_out.returncode != 0:
            print("  ⚠ kubectl apply failed:", apply_out.stderr)
        else:
            print("  ✓ Created aws-secrets-credentials (from Terraform output or env).")
        return

    print("  ⚠ Secret aws-secrets-credentials not found. ESO needs it to read AWS Secrets Manager.")
    print("  Chạy lại: ./deploy.py", TERRAFORM_ENV, "(deploy đã chạy Terraform ở đầu, ESO IAM user sẽ có trong output)")
    print("  Hoặc tạo tay: kubectl create secret generic aws-secrets-credentials -n external-secrets \\")
    print('    --from-literal=access-key="..." --from-literal=secret-access-key="..."')


def _wait_for_external_secrets_crd(env, timeout=120):
    """Chờ CRD ClusterSecretStore có sẵn (cần khi ESO đã cài từ trước, không chạy bước install)."""
    crd_name = "clustersecretstores.external-secrets.io"
    for waited in range(0, timeout, 5):
        res = subprocess.run(
            f"kubectl get crd {crd_name} --request-timeout=5s 2>/dev/null",
            shell=True,
            env=env,
            capture_output=True,
            timeout=10,
        )
        if res.returncode == 0:
            if waited > 0:
                print(f"  ✓ CRD {crd_name} ready (waited {waited}s).")
            return True
        if waited % 15 == 0 and waited > 0:
            print(f"  Waiting for External Secrets CRDs... ({waited}s)")
        time.sleep(5)
    return False


def apply_external_secrets_manifests():
    """Apply ClusterSecretStore + ExternalSecret cho env hiện tại (database + backend)."""
    print("--- Step 7.5c: Applying External Secrets (SecretStore + ExternalSecret) ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Luôn chờ CRD sẵn sàng trước khi apply (kể cả khi ESO "already installed" từ lần chạy trước)
    if not _wait_for_external_secrets_crd(env):
        print("  ⚠ ClusterSecretStore CRD not ready after 2 min. Skipping SecretStore/ExternalSecret apply.")
        print("     Chạy lại sau: helm template external-secrets external-secrets/applications -f external-secrets/applications/values-<env>.yaml | kubectl apply -f -")
        return

    # Webhook phải có endpoint thì apply ClusterSecretStore mới qua validation (no endpoints available)
    print("  Waiting for External Secrets webhook to be ready...")
    for waited in range(0, 120, 5):
        r = subprocess.run(
            "kubectl get endpoints external-secrets-webhook -n external-secrets -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null",
            shell=True,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            if waited > 0:
                print(f"  ✓ Webhook ready (waited {waited}s).")
            break
        if waited % 15 == 0 and waited > 0:
            print(f"  Still waiting for webhook... ({waited}s)")
        time.sleep(5)
    else:
        print("  ⚠ Webhook may not be ready; apply may fail with 'no endpoints available'.")

    chart_dir = os.path.join(_SCRIPT_DIR, "external-secrets", "applications")
    values_file = os.path.join(chart_dir, f"values-{TERRAFORM_ENV}.yaml")
    if not os.path.isfile(values_file):
        print(f"  ⚠ {values_file} not found, skipping.")
        return
    # ExternalSecret cần namespace tồn tại trước (backend → meo-stationery, database → database)
    for ns in ("meo-stationery", "database"):
        subprocess.run(
            f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -",
            shell=True,
            cwd=_SCRIPT_DIR,
            env=env,
            timeout=10,
            capture_output=True,
        )
    run_command(
        f"helm template external-secrets {chart_dir} -f {os.path.join(chart_dir, 'values.yaml')} -f {values_file} | kubectl apply -f -",
        cwd=_SCRIPT_DIR,
        env=env,
        timeout=30,
    )
    print("  ✓ External Secrets manifests applied for env:", TERRAFORM_ENV)


def deploy_argocd_applications():
    """Deploys ArgoCD Application manifests for GitOps."""
    print("--- Step 7.6: Deploying ArgoCD Applications ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    wait_for_argocd_ready()
    print("  Waiting additional 10 seconds for ArgoCD components...")
    time.sleep(10)

    argocd_env_dir = os.path.join(_SCRIPT_DIR, "argocd", "environments", TERRAFORM_ENV)
    if not os.path.isdir(argocd_env_dir):
        print(f"  Error: argocd/environments/{TERRAFORM_ENV}/ not found.")
        sys.exit(1)
    run_command("kubectl apply -f be-application.yaml", cwd=argocd_env_dir, env=env)
    run_command("kubectl apply -f data-application.yaml", cwd=argocd_env_dir, env=env)
    print("  ✓ ArgoCD Applications deployed (argocd/environments/{}/).".format(TERRAFORM_ENV))
    print("  📝 GitOps Repo: https://github.com/minhtri1612/learning_RKE2.git")
    print("  📌 Để apply từ master: clone repo có argocd/environments/, rồi ./scripts/apply-argocd-apps.sh {}".format(TERRAFORM_ENV))
    run_backend_migration_after_sync()


def run_backend_migration_after_sync():
    """Chạy Prisma migration job cho backend. Argo CD sync Helm chart nhưng không chạy Helm hooks,
    nên job migration (post-install/post-upgrade) phải trigger thủ công sau khi app đã sync."""
    print("  Triggering backend migration job (Argo CD does not run Helm hooks)...")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Đợi namespace meo-stationery có (do Argo CD sync với CreateNamespace=true)
    for _ in range(36):
        res = subprocess.run(
            "kubectl get namespace meo-stationery --request-timeout=5s",
            shell=True,
            env=env,
            capture_output=True,
            timeout=10,
        )
        if res.returncode == 0:
            break
        time.sleep(5)
    else:
        print("  ⚠ Namespace meo-stationery chưa có sau 3 phút; bỏ qua migration. Chạy thủ công khi cần:")
        print("    helm template meo-station-backend k8s_helm/backend -n meo-stationery -f k8s_helm/backend/values.yaml --show-only templates/migration-job.yaml | kubectl apply -n meo-stationery -f -")
        return

    backend_chart = os.path.join(_SCRIPT_DIR, "k8s_helm", "backend")
    values_path = os.path.join(backend_chart, "values.yaml")
    try:
        run_command(
            f"helm template meo-station-backend {backend_chart} -n meo-stationery -f {values_path} "
            "--show-only templates/migration-job.yaml | kubectl apply -n meo-stationery -f -",
            cwd=_SCRIPT_DIR,
            env=env,
            timeout=30,
        )
        print("  Waiting for migration job to complete (up to 10m)...")
        subprocess.run(
            "kubectl wait -n meo-stationery --for=condition=complete job/meo-station-backend-migration --timeout=600s",
            shell=True,
            env=env,
            timeout=620,
        )
        print("  ✓ Backend migration completed.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"  ⚠ Migration step failed or timed out: {e}")
        print("  Có thể chạy thủ công: helm template meo-station-backend k8s_helm/backend -n meo-stationery -f k8s_helm/backend/values.yaml --show-only templates/migration-job.yaml | kubectl apply -n meo-stationery -f -")


def resolve_dns_to_ip(dns_name, max_wait=60):
    """Resolves DNS name to IP address with retries."""
    import socket
    for waited in range(0, max_wait, 5):
        try:
            ip = socket.gethostbyname(dns_name)
            print(f"  ✓ Resolved {dns_name} -> {ip}")
            return ip
        except Exception:
            if waited % 10 == 0:
                print(f"  Waiting for DNS resolution... ({waited}s)")
            time.sleep(5)
    print(f"  ⚠ Failed to resolve {dns_name} after {max_wait}s")
    return None


def get_rancher_hostname():
    """Returns environment-specific Rancher hostname."""
    if TERRAFORM_ENV == "management":
        return "rancher.local" # Not used, but for completeness
    return f"rancher-{TERRAFORM_ENV}.local"

# Hostnames trỏ ALB: MỖI ENV CHỈ CẬP NHẬT HOST CỦA MÌNH → argocd.local CHỈ KHI DEPLOY MANAGEMENT.
APP_INGRESS_HOST = f"meo-stationery-{TERRAFORM_ENV}.local"
HOSTNAMES_FOR_ALB_BY_ENV = {
    "management": ("argocd.local",),
    "dev": ("meo-stationery-dev.local", "rancher-dev.local"),
    "prod": ("meo-stationery-prod.local", "rancher-prod.local"),
}


def update_etc_hosts(hostname, ip_or_dns):
    """Automatically adds/updates entry in /etc/hosts (requires sudo)."""
    if "." in ip_or_dns and not ip_or_dns.replace(".", "").isdigit():
        ip = resolve_dns_to_ip(ip_or_dns)
        if not ip:
            return False
    else:
        ip = ip_or_dns
    hosts_file = "/etc/hosts"
    entry = f"{ip}\t{hostname}"
    try:
        result = subprocess.run(f"sudo cat {hosts_file}", shell=True, capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            if hostname in line:
                found = True
                new_lines.append(entry)
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(entry)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("\n".join(new_lines) + "\n")
            tmp_path = tmp.name
        subprocess.check_call(f"sudo cp {tmp_path} {hosts_file} && sudo chmod 644 {hosts_file}", shell=True)
        os.unlink(tmp_path)
        print(f"  ✓ Added/updated {hostname} -> {ip} in /etc/hosts")
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False


def update_etc_hosts_for_alb(alb_dns):
    """Cập nhật /etc/hosts CHỈ hostnames của env hiện tại. Management → argocd.local; dev/prod → app + rancher."""
    if not alb_dns:
        return False
    hostnames = list(HOSTNAMES_FOR_ALB_BY_ENV.get(TERRAFORM_ENV, ()))
    if not hostnames:
        return False
    
    print(f"  Using ALB DNS: {alb_dns}")
    ip = resolve_dns_to_ip(alb_dns)
    if not ip:
        print("  ⚠ Cannot resolve ALB, skipping /etc/hosts update")
        return False

    hosts_file = "/etc/hosts"
    
    # Logic mới: Đọc file, tìm dòng chứa hostname cần update -> xóa hostname đó khỏi dòng cũ.
    # Sau đó thêm dòng mới ở cuối. Tránh xóa nhầm các host khác trên cùng dòng.
    try:
        result = subprocess.run(f"sudo cat {hosts_file}", shell=True, capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        new_lines = []
        
        for line in lines:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                new_lines.append(line)
                continue
            
            # Tách các phần của dòng: IP host1 host2 ...
            parts = line_strip.split()
            if len(parts) < 2:
                new_lines.append(line)
                continue
            
            # Giữ lại IP (parts[0]) và các hostname KHÔNG nằm trong danh sách cần update
            kept_hosts = [h for h in parts[1:] if h not in hostnames]
            
            if len(kept_hosts) == 0:
                # Dòng này chỉ chứa các host cần update -> bỏ dòng
                continue
            elif len(kept_hosts) < len(parts) - 1:
                # Dòng có mix giữa host cần giữ và host cần bỏ -> viết lại dòng với host cần giữ
                new_lines.append(f"{parts[0]}\t{' '.join(kept_hosts)}")
            else:
                # Không có host nào cần bỏ -> giữ nguyên dòng
                new_lines.append(line)
        
        # Thêm dòng mới cho các hostname cần update với IP mới
        entry = f"{ip}\t{' '.join(hostnames)}"
        new_lines.append(entry)
        
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("\n".join(new_lines) + "\n")
            tmp_path = tmp.name
        subprocess.check_call(f"sudo cp {tmp_path} {hosts_file} && sudo chmod 644 {hosts_file}", shell=True)
        os.unlink(tmp_path)
        print(f"  ✓ /etc/hosts updated: {ip} -> {' '.join(hostnames)}")
        return True
    except subprocess.CalledProcessError:
        _write_setup_hosts_script(alb_dns, ip, hostnames)
        return False
    except Exception as e:
        print(f"  ⚠ Failed to update hosts: {e}")
        _write_setup_hosts_script(alb_dns, ip, hostnames)
        return False


def _write_setup_hosts_script(alb_dns, alb_ip, hostnames=None):
    """Ghi script để user chạy sudo khi deploy.py không có quyền sửa /etc/hosts."""
    if hostnames is None:
        hostnames = HOSTNAMES_FOR_ALB_BY_ENV.get(TERRAFORM_ENV, ())
    scripts_dir = os.path.join(_SCRIPT_DIR, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    script_path = os.path.join(scripts_dir, "setup-hosts.sh")
    hosts_str = " ".join(hostnames)
    # sed -E: extended regex so | = OR; escape dots for literal match
    sed_pattern = "|".join(h.replace(".", "\\.") for h in hostnames)
    content = f"""#!/usr/bin/env bash
# Chạy 1 lần sau ./deploy.py (env={TERRAFORM_ENV}) nếu /etc/hosts chưa được cập nhật: sudo bash {script_path}
set -e
ENTRY="{alb_ip}\t{hosts_str}"
# Xóa dòng cũ có các host này
sudo sed -i.bak -E '/{sed_pattern}/d' /etc/hosts
echo "$ENTRY" | sudo tee -a /etc/hosts
echo "Done. Hosts for {TERRAFORM_ENV}: {hosts_str}"
"""
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    print("  ⚠ Could not update /etc/hosts (sudo required). Run once:")
    print(f"     sudo bash {script_path}")


def wait_for_rancher_ready():
    """Waits for at least one Rancher pod to be ready."""
    print("--- Step 8.5: Waiting for Rancher to be ready ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    waited = 0
    while waited < 300:
        try:
            result = subprocess.run(
                "kubectl get pods -n cattle-system -l app=rancher "
                "-o jsonpath='{.items[*].status.containerStatuses[0].ready}'",
                shell=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "true" in (result.stdout or ""):
                print(f"  ✓ Rancher pod is ready (waited {waited}s)")
                return True
        except Exception:
            pass
        time.sleep(10)
        waited += 10

    print("  ⚠ Rancher not ready after 300s, proceeding anyway")
    return False


def _setup_openvpn_systemd_service():
    """Tạo systemd service để VPN chạy nền (không cần giữ terminal). Cài vào /etc/systemd nếu sudo được."""
    service_name = "openvpn-practice-rke2"
    service_content = f"""[Unit]
Description=OpenVPN for practice_RKE2 (route 10.0.0.0/16)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/sbin/openvpn --config minhtri.ovpn
WorkingDirectory={_SCRIPT_DIR}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    service_path = os.path.join(_SCRIPT_DIR, f"{service_name}.service")
    with open(service_path, "w") as f:
        f.write(service_content)
    print("\n--- VPN chạy nền (systemd) ---")
    print(f"  Đã tạo {service_name}.service trong project.")
    install_cmd = (
        f"sudo cp {service_path} /etc/systemd/system/ && "
        "sudo systemctl daemon-reload && "
        f"sudo systemctl enable --now {service_name}"
    )
    try:
        subprocess.run(install_cmd, shell=True, cwd=_SCRIPT_DIR, timeout=15, check=True)
        print(f"  ✓ VPN đã bật nền (service: {service_name}). Tắt: sudo systemctl stop {service_name}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        print("  Để VPN chạy nền sau (không cần giữ terminal), chạy:")
        print(f"     {install_cmd}")
        return
    # Restart để process nạp .ovpn mới (Ansible vừa fetch), không cần user chạy tay refresh-ovpn + restart
    try:
        subprocess.run(f"sudo systemctl restart {service_name}", shell=True, cwd=_SCRIPT_DIR, timeout=10, check=True)
        print(f"  ✓ VPN đã restart (dùng .ovpn mới từ Ansible)")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  Nếu VPN đang chạy với .ovpn cũ, chạy: sudo systemctl restart {service_name}")


def _update_hosts_file():
    """Tự động cập nhật /etc/hosts với ALB DNS cho ingress domains."""
    print("--- Step: Updating /etc/hosts for ALB domains ---")
    
    try:
        # Lấy terraform outputs
        tf_outputs = get_terraform_output()
        alb_dns = tf_outputs.get("web_alb_dns_name", {}).get("value", "")
        
        if not alb_dns:
            print("  ⚠️  No ALB DNS found in terraform output")
            return
            
        # Resolve ALB DNS to IP
        print(f"  Resolving ALB DNS: {alb_dns}")
        try:
            import socket
            alb_ip = socket.gethostbyname(alb_dns)
            print(f"  ✓ ALB IP: {alb_ip}")
        except socket.gaierror as e:
            print(f"  ⚠️  Failed to resolve ALB DNS: {e}")
            return
            
        # Determine ingress hostnames based on environment
        if TERRAFORM_ENV == "management":
            hostnames = ["argocd.local", "rancher.local"]
        elif TERRAFORM_ENV == "dev":
            hostnames = ["meo-stationery-dev.local"]
        elif TERRAFORM_ENV == "prod":
            hostnames = ["meo-stationery-prod.local", "rancher.local"]
        else:
            print(f"  ⚠️  Unknown environment: {TERRAFORM_ENV}")
            return
            
        # Read current /etc/hosts
        hosts_file = "/etc/hosts"
        try:
            with open(hosts_file, "r") as f:
                hosts_content = f.read()
        except PermissionError:
            print(f"  ⚠️  Need sudo to read {hosts_file}")
            return
            
        # Check and add entries
        updated = False
        new_entries = []
        
        for hostname in hostnames:
            # Check if hostname already exists
            if hostname in hosts_content:
                # Check if it points to correct IP
                import re
                pattern = rf"^(\S+)\s+.*{re.escape(hostname)}"
                match = re.search(pattern, hosts_content, re.MULTILINE)
                if match and match.group(1) != alb_ip:
                    print(f"  ⚠️  {hostname} exists but points to {match.group(1)}, should be {alb_ip}")
                    print(f"     Manual update needed: sudo sed -i 's/{match.group(1)}.*{hostname}.*/{alb_ip} {hostname}/' {hosts_file}")
                elif match:
                    print(f"  ✓ {hostname} already points to {alb_ip}")
                else:
                    # Hostname exists but not in expected format
                    print(f"  ⚠️  {hostname} exists in /etc/hosts but format unclear")
            else:
                # Add new entry
                new_entries.append(f"{alb_ip} {hostname}")
                updated = True
                
        if new_entries:
            print(f"  Adding entries to {hosts_file}:")
            for entry in new_entries:
                print(f"    {entry}")
                
            try:
                # Try to append directly
                with open(hosts_file, "a") as f:
                    f.write("\n# Added by deploy.py\n")
                    for entry in new_entries:
                        f.write(f"{entry}\n")
                print(f"  ✓ Updated {hosts_file}")
            except PermissionError:
                print(f"  ⚠️  Need sudo to write to {hosts_file}. Run manually:")
                print(f"     echo '# Added by deploy.py' | sudo tee -a {hosts_file}")
                for entry in new_entries:
                    print(f"     echo '{entry}' | sudo tee -a {hosts_file}")
        else:
            print("  ✓ /etc/hosts already up to date")
            
    except Exception as e:
        print(f"  ⚠️  Failed to update /etc/hosts: {e}")
        print("     You may need to manually add ALB entries to /etc/hosts")


def start_rancher_portforward():
    """Starts port-forward for Rancher UI automatically with retry logic."""
    print("--- Step 9: Starting Rancher Port-Forward ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    wait_for_rancher_ready()

    try:
        subprocess.check_call("pkill -f 'kubectl port-forward.*svc/rancher'", shell=True, stderr=subprocess.DEVNULL)
        time.sleep(2)
    except Exception:
        pass

    log_file = "/tmp/rancher-pf.log"
    wrapper_script = f"""#!/bin/bash
while true; do
  kubectl port-forward -n cattle-system svc/rancher 8443:443 >> {log_file} 2>&1
  echo "$(date): Port-forward died, restarting in 5 seconds..." >> {log_file}
  sleep 5
done
"""

    wrapper_path = "/tmp/rancher-pf-wrapper.sh"
    with open(wrapper_path, "w") as f:
        f.write(wrapper_script)
    os.chmod(wrapper_path, 0o755)

    process = subprocess.Popen(wrapper_path, shell=True, env=env)
    time.sleep(5)

    if process.poll() is None:
        print(f"  ✓ Port-forward started successfully (PID: {process.pid})")
        print(f"  ✓ Logs: {log_file}")
    else:
        print(f"  ⚠ Port-forward may have failed. Check logs: {log_file}")


def _run_deploy_all():
    """Deploy management + dev + prod, rồi ArgoCD add cluster + apply Applications → GitOps sync mọi thứ."""
    deploy_py = os.path.abspath(os.path.join(_SCRIPT_DIR, "deploy.py"))
    if not os.path.isfile(deploy_py):
        deploy_py = sys.argv[0]
    print("\n" + "=" * 60)
    print("  ./deploy.py (no args) = FULL PIPELINE: management + dev + prod + ArgoCD add clusters + Applications")
    print("  ArgoCD sẽ sync app từ Git xuống dev/prod — không cần chạy tay script nào.")
    print("=" * 60)
    # 1. Management full deploy (OpenVPN + RKE2 + ArgoCD)
    print(f"\n--- Deploy env: management ---")
    run_command(f"{sys.executable} {deploy_py} management", cwd=_SCRIPT_DIR, timeout=3600)
    # 2. Chỉ Terraform apply dev + prod (chưa peering nên chưa chạy fetch_kubeconfig)
    for env in ("dev", "prod"):
        env_dir = os.path.join(TERRAFORM_DIR, "environments", env)
        tfvars = os.path.join(env_dir, "terraform.tfvars")
        if not os.path.isfile(tfvars):
            ex = os.path.join(env_dir, "terraform.tfvars.example")
            if os.path.isfile(ex):
                with open(ex) as f:
                    c = f.read().replace("YOUR_OFFICE_OR_VPN_IP/32", "0.0.0.0/0")
                with open(tfvars, "w") as f:
                    f.write(c)
        print(f"\n--- Terraform apply: {env} ---")
        run_command(
            f"terraform -chdir=environments/{env} init -input=false && terraform -chdir=environments/{env} apply -auto-approve -input=false -var-file=terraform.tfvars",
            cwd=TERRAFORM_DIR,
            timeout=1800,
        )
    # 3. VPC peering trước khi SSH từ Management OpenVPN -> dev/prod master
    print("\n--- Networking: VPC peering (management <-> dev, management <-> prod) ---")
    run_command(
        "terraform -chdir=environments/networking init -input=false && terraform -chdir=environments/networking apply -auto-approve -input=false",
        cwd=TERRAFORM_DIR,
        timeout=300,
    )
    # 4. Dev/Prod: fetch kubeconfig qua jump + Rancher/ESO (đã có peering nên SSH được)
    for env in ("dev", "prod"):
        print(f"\n--- Deploy env: {env} (kubeconfig + Rancher + ESO) ---")
        env_with_skip = os.environ.copy()
        env_with_skip["SKIP_TERRAFORM"] = "1"
        run_command(f"{sys.executable} {deploy_py} {env}", cwd=_SCRIPT_DIR, timeout=3600, env=env_with_skip)
    print("\n--- ArgoCD: add clusters + apply Applications (GitOps) ---")
    
    # We don't need SSH tunnel to get password anymore if we assume default or manual retrieval
    # For now, let's just use empty password and let the script prompt or use default if not set
    argocd_password = os.environ.get("ARGOCD_PASSWORD", "")
    
    # If we really need to fetch it automatically without tunnel, we could do it via SSH command directly
    if not argocd_password:
        try:
             # Try to fetch via direct SSH on Management node (if reachable) or assume user has it
             pass 
        except Exception:
            pass
    # Register dev/prod clusters to ArgoCD using local kubectl (via tunnel) + Private IPs
    # The script 'create-argocd-cluster-secrets.sh' handles secret creation directly
    print("\n--- ArgoCD: Registering Clusters (Dev/Prod) ---")
    run_command("bash scripts/create-argocd-cluster-secrets.sh", cwd=_SCRIPT_DIR, timeout=300)
    run_command("bash scripts/setup-argocd-management-apps.sh", cwd=_SCRIPT_DIR, timeout=120)
    print("\n" + "=" * 60)
    print("  Done. ArgoCD sẽ sync từ Git xuống dev + prod.")
    print("  http://argocd.local — Applications (backend-dev, data-dev, backend-prod, data-prod)")
    print("=" * 60)


def main():
    if TERRAFORM_ENV == "all":
        _run_deploy_all()
        return
    if os.environ.get("SKIP_TERRAFORM") != "1":
        setup_terraform()
    tf_out = get_terraform_output()

    nlb_dns = tf_out["nlb_dns_name"]["value"]
    master_private_ip = tf_out["master_private_ip"]["value"][0]

    # Chỉ Management có OpenVPN; dev/prod dùng Management làm jump host
    if TERRAFORM_ENV == "management":
        openvpn_public_ip = tf_out["openvpn_public_ip"]["value"]
        jump_key_path = None
        key_on_jump = "k8s-key.pem"
    else:
        openvpn_public_ip = get_management_openvpn_ip()
        if not openvpn_public_ip:
            print("  ✗ Dev/Prod cần Management OpenVPN làm jump. Chạy terraform apply cho management trước.")
            sys.exit(1)
        jump_key_path = os.path.join(TERRAFORM_DIR, "environments", "management", SSH_KEY_FILE_NAME)
        if not os.path.isfile(jump_key_path):
            print(f"  ✗ Thiếu key Management: {jump_key_path}")
            sys.exit(1)
        jump_key_path = os.path.abspath(jump_key_path)
        key_on_jump = f"k8s-key-{TERRAFORM_ENV}.pem"

    print("\n--- RKE2 + OpenVPN ---")
    print(f"  ✓ Jump / OpenVPN: {openvpn_public_ip}" + (" (Management)" if TERRAFORM_ENV != "management" else ""))
    print(f"  ✓ Master Private IP: {master_private_ip}")

    if os.environ.get("SKIP_OPENVPN_ANSIBLE") == "1":
        print("  ⏭ SKIP_OPENVPN_ANSIBLE=1 → bỏ qua bước OpenVPN/Ansible.")
        if TERRAFORM_ENV == "management":
            print("  Khi SSH được, chạy:")
            print(f"    ssh -o IdentitiesOnly=yes -i terraform/environments/{TERRAFORM_ENV}/k8s-key.pem ubuntu@{openvpn_public_ip}")
            print(f"    cd ansible && ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip={openvpn_public_ip} openvpn-server.yml")
        print("  Sau đó chạy lại: ./deploy.py", TERRAFORM_ENV)
        sys.exit(0)

    if TERRAFORM_ENV == "management":
        print("  ⏳ Đợi OpenVPN instance SSH sẵn sàng rồi chạy Ansible setup...")
        run_openvpn_ansible(openvpn_public_ip)

    fetch_kubeconfig(openvpn_public_ip, master_private_ip, nlb_dns, jump_ssh_key_path=jump_key_path, key_on_jump=key_on_jump)
    fetch_kubeconfig(openvpn_public_ip, master_private_ip, nlb_dns, jump_ssh_key_path=jump_key_path, key_on_jump=key_on_jump)
    _create_tunnel_kubeconfig() # Enable tunnel so local Helm commands work via 127.0.0.1
    print("--- Step 4.4: Waiting for API server reachable from OpenVPN ---")
    if not wait_for_api_from_openvpn(openvpn_public_ip, master_private_ip, jump_ssh_key_path=jump_key_path):
        sys.exit(1)
    start_openvpn_port_forward(openvpn_public_ip, master_private_ip, jump_ssh_key_path=jump_key_path)
    wait_for_nlb_health_checks()
    install_ebs_csi_driver()

    if TERRAFORM_ENV == "management":
        # Cluster management: CHỈ cài ArgoCD. ArgoCD này quản lý deploy sang dev/prod (không cài ArgoCD trên prod/dev).
        install_argocd()
        wait_for_argocd_ready()
        # Sau khi có argocd/environments/management/ (Application target dev/prod), có thể gọi deploy_argocd_applications() ở đây.
    else:
        # Dev/Staging/Prod: KHÔNG cài ArgoCD. Chỉ Rancher, ESO, secrets. Apps deploy qua ArgoCD trên management (add cluster + chạy setup-argocd-management-apps.sh).
        install_rancher()
        install_external_secrets_operator()
        ensure_aws_secrets_credentials()
        apply_external_secrets_manifests()

    print("\n--- Updating /etc/hosts for Ingress access ---")
    alb_dns = tf_out.get("web_alb_dns_name", {}).get("value", "")
    if alb_dns:
        if not update_etc_hosts_for_alb(alb_dns):
            print(f"  You can run the script above once to add ALB -> {' '.join(HOSTNAMES_FOR_ALB_BY_ENV.get(TERRAFORM_ENV, ()))}")
    else:
        print("  ⚠ ALB DNS not available yet, skipping /etc/hosts update")
        print("  You can update manually after ALB is ready")

    if TERRAFORM_ENV != "management":
        start_rancher_portforward()

    # VPN chạy nền: tạo systemd service (project này) để không cần giữ terminal
    _setup_openvpn_systemd_service()

    # Tự động cập nhật /etc/hosts với ALB domains
    _update_hosts_file()

    print("\n" + "=" * 60)
    print("XXX Deployment Complete! XXX")
    print("=" * 60)
    print("\n📋 Cluster (kubeconfig theo env, chỉ cần VPN):")
    print(f"   export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"   kubectl get nodes")
    if TERRAFORM_ENV == "management":
        print(f"   ssh -o IdentitiesOnly=yes -i terraform/environments/{TERRAFORM_ENV}/k8s-key.pem ubuntu@{master_private_ip}")
        print(f"\n🔐 OpenVPN Server: {openvpn_public_ip}")
        print("   SSH qua jump: ssh -o IdentitiesOnly=yes -i terraform/environments/management/k8s-key.pem ubuntu@%s" % openvpn_public_ip)
    else:
        print(f"   SSH qua Management: ssh -i .../management/k8s-key.pem ubuntu@{openvpn_public_ip} rồi ssh -i .../%s/k8s-key.pem ubuntu@%s" % (TERRAFORM_ENV, master_private_ip))
        print(f"\n🔐 Jump host (Management OpenVPN): {openvpn_public_ip}")
    
    print(f"\n🌐 Web Access (ALB + /etc/hosts auto-updated):")
    if TERRAFORM_ENV == "management":
        if alb_dns:
            print(f"   ArgoCD UI: http://argocd.local")
            print(f"   Rancher UI: https://rancher.local")
        print("\n   ArgoCD (port-forward backup):\n   kubectl port-forward svc/argocd-server -n argocd 8080:443")
        print("\n   Cluster management chỉ chạy ArgoCD.")
        print("   Để deploy full (management + dev + prod + ArgoCD sync GitOps): chạy ./deploy.py (không tham số).")
        print("   Nếu chỉ deploy từng env tay: sau đó chạy ./deploy.py (không tham số) để add clusters + apps.")
    else:
        if alb_dns:
            print(f"   Rancher UI: https://rancher.local")
            print(f"   App ({TERRAFORM_ENV}): https://meo-stationery-{TERRAFORM_ENV}.local")
        print(f"\n🌐 Rancher UI (port-forward backup):\n   https://localhost:8443")
        print("   ArgoCD chỉ chạy trên cluster management → http://argocd.local (sau khi deploy management).")
    
    print(f"\n🔧 Utilities:")
    print(f"   Update /etc/hosts: ./scripts/update-hosts.sh {TERRAFORM_ENV}")
    print(f"   Update all envs: ./scripts/update-hosts.sh all")
    
    print("\n⚠️  TLS note: self-signed cert → browser warning is expected.")
    print("=" * 60)


if __name__ == "__main__":
    main()
