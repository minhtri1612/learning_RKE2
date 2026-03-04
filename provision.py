#!/usr/bin/env python3
"""
Phase 1 — KHÔNG cần VPN (No VPN Required)
==========================================
Tạo hạ tầng AWS (Terraform) và cấu hình OpenVPN Server (Ansible).
Cuối bước này, file .ovpn sẽ được download về project root.

Usage:
    ./provision.py [dev|prod|management]   (mặc định: management)

Sau khi chạy xong:
    1. Bật VPN: sudo openvpn --config minhtri.ovpn
    2. Chạy Phase 2: ./configure.py [env]
"""
import json
import os
import re
import subprocess
import sys
import time

# ── Cấu hình ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAFORM_DIR = os.path.join(_SCRIPT_DIR, "terraform")
ANSIBLE_DIR = os.path.join(_SCRIPT_DIR, "ansible")

_VALID_ENVS = ("dev", "prod", "management")
SSH_KEY_FILE_NAME = "k8s-key.pem"


def _get_env():
    if len(sys.argv) >= 2:
        env = sys.argv[1].lower()
        if env in _VALID_ENVS:
            return env
        print(f"Usage: {sys.argv[0]} [dev|prod|management]", file=sys.stderr)
        print(f"Invalid environment: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    return os.environ.get("TF_ENV", "management")


TERRAFORM_ENV = _get_env()
TERRAFORM_ENV_DIR = os.path.join(TERRAFORM_DIR, "environments", TERRAFORM_ENV)
KUBECONFIG_FILE = os.path.join(_SCRIPT_DIR, f"kube_config_rke2_{TERRAFORM_ENV}.yaml")


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


def get_management_openvpn_ip():
    """Lấy OpenVPN public IP của management (jump host cho dev/prod)."""
    try:
        out = subprocess.check_output(
            "terraform -chdir=environments/management output -json",
            shell=True, cwd=TERRAFORM_DIR, timeout=15,
        )
        data = json.loads(out)
        return data.get("openvpn_public_ip", {}).get("value", "")
    except Exception:
        return ""


# ── Phase 1 Functions ─────────────────────────────────────────────────────────
def setup_terraform():
    """Chạy terraform apply cho env hiện tại."""
    tfvars = os.path.join(TERRAFORM_ENV_DIR, "terraform.tfvars")
    if not os.path.isfile(tfvars):
        example = os.path.join(TERRAFORM_ENV_DIR, "terraform.tfvars.example")
        if os.path.isfile(example):
            with open(example, "r") as f:
                content = f.read()
            content = content.replace("YOUR_OFFICE_OR_VPN_IP/32", "0.0.0.0/0")
            with open(tfvars, "w") as f:
                f.write(content)
            print(f"Created {tfvars} from .example (my_ip=0.0.0.0/0). Edit for production.")
        else:
            print(f"Error: terraform.tfvars not found in {TERRAFORM_ENV}.")
            sys.exit(1)
    print("--- Step 1: Terraform Apply ---")
    run_command(f"terraform -chdir=environments/{TERRAFORM_ENV} init -input=false", cwd=TERRAFORM_DIR)
    run_command(
        f"terraform -chdir=environments/{TERRAFORM_ENV} apply -auto-approve -input=false -var-file=terraform.tfvars",
        cwd=TERRAFORM_DIR,
    )


def setup_networking():
    """Apply networking terraform để tạo/cập nhật VPC peering giữa management, dev, prod.
    Phải chạy sau khi env VPC đã tạo xong, trước khi fetch_kubeconfig().
    Skip với SKIP_NETWORKING=1."""
    if os.environ.get("SKIP_NETWORKING") == "1":
        print("  ⏭ SKIP_NETWORKING=1 → bỏ qua VPC peering.")
        return
    networking_dir = os.path.join(TERRAFORM_DIR, "environments", "networking")
    if not os.path.isdir(networking_dir):
        print("  ⚠ Không tìm thấy environments/networking → bỏ qua VPC peering.")
        return
    print("--- Step 2: VPC Peering (networking terraform) ---")
    subprocess.run(
        "terraform -chdir=environments/networking init -input=false",
        shell=True, cwd=TERRAFORM_DIR, capture_output=True,
    )
    run_command(
        "terraform -chdir=environments/networking apply -auto-approve -input=false",
        cwd=TERRAFORM_DIR,
    )
    print("  ✓ VPC Peering applied.")


def run_openvpn_ansible(openvpn_public_ip):
    """Chạy Ansible playbook để cấu hình OpenVPN và tạo .ovpn file (download về project root)."""
    print("--- Step 2: Ansible OpenVPN Server Setup ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    max_wait = 300
    print(f"  Waiting for OpenVPN instance to accept SSH (tối đa {max_wait // 60} phút)...")
    ssh_ok = False
    for waited in range(0, max_wait, 10):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{openvpn_public_ip} 'echo ready'",
                shell=True, capture_output=True, timeout=15,
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
        print(f"  ✗ OpenVPN server SSH timeout after {max_wait}s.")
        print(f"  Kiểm tra SSH thủ công: ssh -o IdentitiesOnly=yes -i {ssh_key_path} ubuntu@{openvpn_public_ip}")
        sys.exit(1)

    vpn_server_yml = os.path.join(ANSIBLE_DIR, "group_vars", "vpn_server.yml")
    with open(vpn_server_yml, "r") as f:
        vpn_cfg = f.read()
    key_line = f'ansible_ssh_private_key_file: "{ssh_key_path}"'
    if "ansible_ssh_private_key_file" in vpn_cfg:
        vpn_cfg = re.sub(r"ansible_ssh_private_key_file:\s*[^\n]+", key_line, vpn_cfg)
    else:
        vpn_cfg = vpn_cfg.rstrip() + "\n" + key_line + "\n"
    if "IdentitiesOnly" not in vpn_cfg:
        if "ansible_ssh_common_args:" in vpn_cfg:
            vpn_cfg = re.sub(r'(ansible_ssh_common_args:\s*)"', r'\1"-o IdentitiesOnly=yes ', vpn_cfg)
        else:
            vpn_cfg = vpn_cfg.rstrip() + '\nansible_ssh_common_args: "-o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=30"\n'
    with open(vpn_server_yml, "w") as f:
        f.write(vpn_cfg)

    inventory_path = os.path.join(ANSIBLE_DIR, "inventory_openvpn.yml")
    with open(inventory_path, "w") as f:
        f.write(f"vpn_server:\n  hosts:\n    {openvpn_public_ip}:\n")

    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_PRIVATE_KEY_FILE"] = ssh_key_path
    run_command(
        f"ansible-playbook -i inventory_openvpn.yml -e openvpn_public_ip={openvpn_public_ip} openvpn-server.yml",
        cwd=ANSIBLE_DIR, env=env, timeout=600,
    )
    print("  ✓ OpenVPN server configured; .ovpn file downloaded to project root.")


def fetch_kubeconfig(openvpn_ip, master_private_ip, nlb_dns, jump_ssh_key_path=None, key_on_jump="k8s-key.pem"):
    """Fetch kubeconfig từ master node thông qua OpenVPN server (jump host)."""
    key_to_jump = jump_ssh_key_path or os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    master_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))

    print("--- Step 3: Fetching Kubeconfig via OpenVPN Server (jump) ---")
    print("  Waiting for OpenVPN server to be ready...")
    for waited in range(0, 120, 5):
        try:
            res = subprocess.run(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} 'echo ready'",
                shell=True, capture_output=True, timeout=10,
            )
            if res.returncode == 0:
                print(f"  ✓ OpenVPN server ready (waited {waited}s)")
                break
        except Exception:
            pass
        time.sleep(5)

    print("  Copying SSH key to OpenVPN server...")
    run_command(f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'", timeout=15)
    run_command(f"scp -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -i {key_to_jump} {master_key_path} ubuntu@{openvpn_ip}:~/.ssh/{key_on_jump}", timeout=30)
    run_command(f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'chmod 600 ~/.ssh/{key_on_jump}'", timeout=15)

    print("  Waiting for RKE2 to generate kubeconfig (user_data is running)...")
    time.sleep(180)

    inner_ssh = f"ssh -i ~/.ssh/{key_on_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{master_private_ip}"
    print("  Waiting for SSH to master via jump host...")
    for waited in range(0, 420, 15):
        try:
            res = subprocess.run(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} "
                f"'{inner_ssh} \"test -f /home/ubuntu/.kube/config || sudo test -f /etc/rancher/rke2/rke2.yaml\" && echo ready'",
                shell=True, capture_output=True, timeout=25,
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
            f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} '{inner_ssh} cat /home/ubuntu/.kube/config'",
            shell=True, timeout=30, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError:
        try:
            kubeconfig_content = subprocess.check_output(
                f"ssh -i {key_to_jump} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} '{inner_ssh} sudo cat /etc/rancher/rke2/rke2.yaml'",
                shell=True, timeout=30, stderr=subprocess.PIPE,
            )
            print("  ✓ Used /etc/rancher/rke2/rke2.yaml (fallback)")
        except subprocess.CalledProcessError as e2:
            if e2.stderr:
                print(f"  Fallback failed: {e2.stderr.decode(errors='replace')[:300]}", file=sys.stderr)
            raise

    if not kubeconfig_content:
        raise RuntimeError("Could not fetch kubeconfig from master.")

    with open(KUBECONFIG_FILE, "wb") as f:
        f.write(kubeconfig_content)

    # Patch server URL to private IP + use insecure-skip-tls-verify
    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    config = re.sub(r"server:\s*https://[^\s\n]+", f"server: https://{master_private_ip}:6443", config)
    lines = config.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(r"certificate-authority-data", line):
            indent = len(line) - len(line.lstrip())
            new_lines.append(" " * indent + "insecure-skip-tls-verify: true")
            i += 1
            while i < len(lines) and re.match(r"^\s+[A-Za-z0-9+/=]+$", lines[i]):
                i += 1
            continue
        else:
            new_lines.append(line)
            i += 1
    config = "\n".join(new_lines)
    if "insecure-skip-tls-verify" not in config:
        config = re.sub(r"(server:\s*https://[^\n]+)", r"\1\n    insecure-skip-tls-verify: true", config)
    with open(KUBECONFIG_FILE, "w") as f:
        f.write(config)
    os.chmod(KUBECONFIG_FILE, 0o600)
    print(f"  ✓ Kubeconfig saved to {KUBECONFIG_FILE} (server: https://{master_private_ip}:6443 — cần VPN để truy cập)")


def wait_for_api_from_openvpn(openvpn_ip, master_private_ip, max_wait=600, jump_ssh_key_path=None):
    """Xác minh API server có thể truy cập được từ phía OpenVPN server."""
    key_path = jump_ssh_key_path or os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    print("  Waiting for Kubernetes API reachable from OpenVPN (curl https://master:6443/readyz)...")
    last_out, last_err = "", ""
    for waited in range(0, max_wait, 15):
        try:
            res = subprocess.run(
                f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{openvpn_ip} "
                f"curl -k -s -o /dev/null -w '%{{http_code}}' --connect-timeout 5 https://{master_private_ip}:6443/readyz 2>&1; echo ' exit='$?",
                shell=True, capture_output=True, timeout=20,
            )
            out = (res.stdout or b"").decode(errors="replace").strip()
            err = (res.stderr or b"").decode(errors="replace").strip()
            last_out, last_err = out, err
            if res.returncode == 0 and ("200" in out or "401" in out or "403" in out):
                print(f"  ✓ API reachable from OpenVPN (waited {waited}s)")
                return True
            if waited % 60 == 0 and waited > 0:
                print(f"  Still waiting... ({waited}s) curl: {out[:80] or err[:80]}")
        except subprocess.TimeoutExpired:
            last_err = "ssh/curl timeout"
        except Exception as e:
            last_err = str(e)
        time.sleep(15)
    print(f"  ✗ API not reachable after {max_wait}s. Last: {last_out or last_err}")
    return False


def register_cluster_with_argocd_cli(env, kubeconfig_path, mgmt_kubeconfig):
    """
    Option B — ĐÚ CHUẨN PRODUCTION:
    Đăng ký cluster với ArgoCD qua `argocd cluster add` CLI.
    Credentials (certData, keyData) được inject trực tiếp vào ArgoCD Secret trên cluster
    thông qua ArgoCD API — KHÔNG bao giờ được ghi vào file YAML hoặc commit lên Git.

    Yêu cầu:
    - argocd CLI phải được cài trên máy local hoặc trên management node
    - ArgoCD phải đang chạy trên management cluster (sau configure.py management)
    - VPN phải đang bật
    """
    if env not in ("dev", "prod"):
        return
    if not os.path.isfile(kubeconfig_path):
        print(f"  ⚠ Kubeconfig không tồn tại: {kubeconfig_path} — bỏ qua đăng ký cluster.")
        return
    if not os.path.isfile(mgmt_kubeconfig):
        print(f"  ⚠ Management kubeconfig chưa có — bỏ qua đăng ký (sẽ làm sau configure.py management).")
        return

    # Đọc server URL từ kubeconfig để dùng làm context name cho argocd cluster add
    try:
        import yaml as _yaml
        with open(kubeconfig_path) as f:
            kc = _yaml.safe_load(f)
        server = (kc.get("clusters") or [{}])[0].get("cluster", {}).get("server", "")
        context_name = (kc.get("contexts") or [{}])[0].get("name", env)
    except Exception as e:
        print(f"  ⚠ Không đọc được kubeconfig: {e} — bỏ qua.")
        return

    print(f"--- Option B: Register {env} cluster via argocd cluster add (no keys in Git) ---")
    print(f"  Server: {server}")

    # Lấy ArgoCD admin password để login
    env_vars = os.environ.copy()
    env_vars["KUBECONFIG"] = mgmt_kubeconfig

    password_res = subprocess.run(
        "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d",
        shell=True, capture_output=True, text=True, env=env_vars, timeout=15,
    )
    argocd_password = (password_res.stdout or "").strip()
    if not argocd_password:
        print("  ⚠ Không lấy được ArgoCD admin password. Đăng ký thủ công:")
        print(f"    argocd cluster add {context_name} --name {env} --kubeconfig {kubeconfig_path}")
        return

    # Login ArgoCD (dùng internal svc endpoint từ management cluster)
    login_res = subprocess.run(
        "argocd login argocd-server.argocd.svc.cluster.local:443 "
        f"--username admin --password \"{argocd_password}\" "
        "--insecure --grpc-web",
        shell=True, capture_output=True, text=True, env=env_vars, timeout=30,
    )
    if login_res.returncode != 0:
        # Fallback: login via port-forward
        print("  Trying argocd login via localhost:8080 (port-forward) ...")
        login_res = subprocess.run(
            f"argocd login localhost:8080 "
            f"--username admin --password \"{argocd_password}\" "
            "--insecure",
            shell=True, capture_output=True, text=True, timeout=30,
        )
        if login_res.returncode != 0:
            print("  ⚠ ArgoCD login failed. Đăng ký thủ công:")
            print(f"    argocd login <argocd-server> --username admin")
            print(f"    argocd cluster add {context_name} --name {env} --kubeconfig {kubeconfig_path} --insecure")
            return

    # argocd cluster add: inject credentials trực tiếp vào ArgoCD Secret, không qua Git
    add_res = subprocess.run(
        f"argocd cluster add {context_name} "
        f"--name {env} "
        f"--kubeconfig {kubeconfig_path} "
        "--insecure "
        "--yes",
        shell=True, capture_output=True, text=True, timeout=60,
    )
    if add_res.returncode == 0:
        print(f"  ✓ Cluster '{env}' đã đăng ký với ArgoCD (credentials không vào Git).")
        print(f"  Verify: kubectl get secret cluster-{env} -n argocd --kubeconfig={mgmt_kubeconfig}")
    else:
        err = (add_res.stderr or add_res.stdout or "").strip()[:300]
        print(f"  ⚠ argocd cluster add thất bại: {err}")
        print(f"  Đăng ký thủ công sau khi bật VPN:")
        print(f"    KUBECONFIG={mgmt_kubeconfig}")
        print(f"    argocd cluster add {context_name} --name {env} --kubeconfig {kubeconfig_path} --insecure --yes")



def _try_register_cluster_now(env):
    """
    Thử đăng ký cluster ngay lúc provision nếu management kubeconfig đã có sẵn.
    Thực chất là wrapper gọi register_cluster_with_argocd_cli().
    """
    mgmt_kube = os.path.join(_SCRIPT_DIR, "kube_config_rke2_management.yaml")
    if not os.path.isfile(mgmt_kube):
        print("  ⏭ Management kubeconfig chưa có → bỏ qua đăng ký cluster (sẽ làm sau configure.py management).")
        print(f"  Sau này chạy: argocd cluster add <context> --name {env} --kubeconfig {os.path.abspath(KUBECONFIG_FILE)} --insecure --yes")
        return
    register_cluster_with_argocd_cli(env, os.path.abspath(KUBECONFIG_FILE), mgmt_kube)



# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print(f"  PROVISION — Phase 1 (No VPN Required) — env: {TERRAFORM_ENV}")
    print("=" * 60)

    if os.environ.get("SKIP_TERRAFORM") != "1":
        setup_terraform()
        if TERRAFORM_ENV != "management":
            setup_networking()

    tf_out = get_terraform_output()
    nlb_dns = tf_out["nlb_dns_name"]["value"]
    master_private_ip = tf_out["master_private_ip"]["value"][0]

    if TERRAFORM_ENV == "management":
        openvpn_public_ip = tf_out["openvpn_public_ip"]["value"]
        jump_key_path = None
        key_on_jump = "k8s-key.pem"
    else:
        openvpn_public_ip = get_management_openvpn_ip()
        if not openvpn_public_ip:
            print("  ✗ Dev/Prod cần Management OpenVPN làm jump. Chạy provision.py management trước.")
            sys.exit(1)
        jump_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, "environments", "management", SSH_KEY_FILE_NAME))
        if not os.path.isfile(jump_key_path):
            print(f"  ✗ Thiếu key Management: {jump_key_path}")
            sys.exit(1)
        key_on_jump = f"k8s-key-{TERRAFORM_ENV}.pem"

    print(f"\n  ✓ Jump / OpenVPN: {openvpn_public_ip}")
    print(f"  ✓ Master Private IP: {master_private_ip}")

    if TERRAFORM_ENV == "management":
        run_openvpn_ansible(openvpn_public_ip)

    fetch_kubeconfig(openvpn_public_ip, master_private_ip, nlb_dns, jump_ssh_key_path=jump_key_path, key_on_jump=key_on_jump)

    # Option B: Đăng ký cluster vưới ArgoCD qua CLI — credentials KHÔNG vào Git
    # cluster-dev.yaml / cluster-prod.yaml trong Git chỉ là template placeholder, không chứa key
    if TERRAFORM_ENV in ("dev", "prod"):
        print(f"--- Step 4: Register {TERRAFORM_ENV} cluster with ArgoCD (Option B) ---")
        _try_register_cluster_now(TERRAFORM_ENV)

    print(f"--- Step 5: Verifying API reachable from OpenVPN side ---")
    if not wait_for_api_from_openvpn(openvpn_public_ip, master_private_ip, jump_ssh_key_path=jump_key_path):
        print("  ⚠ API check failed — continue anyway. Kiểm tra Security Group port 6443.")

    print("\n" + "=" * 60)
    print("  ✅ PROVISION COMPLETE!")
    print("=" * 60)
    print(f"\n  Kubeconfig: export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    if TERRAFORM_ENV == "management":
        ovpn_files = [f for f in os.listdir(_SCRIPT_DIR) if f.endswith(".ovpn")]
        ovpn_hint = ovpn_files[0] if ovpn_files else "<username>.ovpn"
        if ovpn_files:
            print(f"\n  🔐 File .ovpn đã sẵn sàng: {', '.join(ovpn_files)}")
        print("\n  ─────────────────────────────────────────")
        print("  ▶ BƯỚC TIẾP THEO:")
        print(f"    1. Bật VPN:      sudo openvpn --config {ovpn_hint}")
        print(f"    2. Configure:    ./configure.py {TERRAFORM_ENV}")
        print("  ─────────────────────────────────────────")
    else:
        print("\n  ─────────────────────────────────────────")
        print("  ▶ BƯOC TIẾP THEO:")
        print("     1. Đảm bảo VPN management đang bật")
        print(f"    2. Configure:    ./configure.py {TERRAFORM_ENV}")
        print(f"    3. Nếu đăng ký cluster chưa xảy ra tự động, chạy thủ công:")
        print(f"       argocd cluster add <context> --name {TERRAFORM_ENV} \\")
        print(f"         --kubeconfig {os.path.abspath(KUBECONFIG_FILE)} --insecure --yes")
        print("  ─────────────────────────────────────────")
    print("=" * 60)


if __name__ == "__main__":
    main()
