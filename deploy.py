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

_VALID_ENVS = ("dev", "staging", "prod")


def _get_terraform_env():
    """dev | staging | prod: từ ./deploy.py <env> hoặc biến môi trường TF_ENV."""
    if len(sys.argv) >= 2:
        env = sys.argv[1].lower()
        if env in _VALID_ENVS:
            return env
        print(f"Usage: {sys.argv[0]} [dev|staging|prod]", file=sys.stderr)
        print(f"Invalid environment: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    return os.environ.get("TF_ENV", "dev")


TERRAFORM_ENV = _get_terraform_env()
TERRAFORM_ENV_DIR = os.path.join(TERRAFORM_DIR, "environments", TERRAFORM_ENV)
ANSIBLE_DIR = os.path.join(_SCRIPT_DIR, "ansible")
HELM_DIR = os.path.join(_SCRIPT_DIR, "k8s_helm")
KUBECONFIG_FILE = os.path.join(_SCRIPT_DIR, "kube_config_rke2.yaml")
SSH_KEY_FILE_NAME = "k8s-key.pem"
# Trong deploy: file tạm 127.0.0.1 cho tunnel; file ghi ra cho user (KUBECONFIG_FILE) = master IP
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
    print("  Waiting for OpenVPN instance to accept SSH (tối đa 5 phút)...")
    ssh_ok = False
    for waited in range(0, 300, 10):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{openvpn_public_ip} 'echo ready'",
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
        print("  ✗ OpenVPN server SSH timeout sau 5 phút.")
        print("     Kiểm tra: Security group openvpn_sg có cho SSH từ IP máy bạn (var.my_ip)?")
        print("     Chạy Ansible thủ công khi instance sẵn sàng:")
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


def fetch_kubeconfig(openvpn_ip, master_private_ip, nlb_dns):
    """Fetches and configures kubeconfig via SSH through OpenVPN server (jump host)."""
    print("--- Step 4: Fetching Kubeconfig via OpenVPN Server (jump) ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))

    print("  Waiting for OpenVPN server to be ready...")
    for waited in range(0, 120, 5):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} 'echo ready'",
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
        f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'",
        timeout=15,
    )
    run_command(
        f"scp -o StrictHostKeyChecking=no -i {ssh_key_path} {ssh_key_path} ubuntu@{openvpn_ip}:~/.ssh/k8s-key.pem",
        timeout=30,
    )
    run_command(
        f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} 'chmod 600 ~/.ssh/k8s-key.pem'",
        timeout=15,
    )

    print("  Waiting for RKE2 to generate kubeconfig (user_data đang chạy)...")
    time.sleep(120)

    print("  Waiting for SSH to master via OpenVPN server...")
    for waited in range(0, 300, 15):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{openvpn_ip} "
                f"'ssh -i ~/.ssh/k8s-key.pem -o StrictHostKeyChecking=no ubuntu@{master_private_ip} "
                "test -f /home/ubuntu/.kube/config && echo ready'",
                shell=True,
                capture_output=True,
                timeout=20,
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
    kubeconfig_content = subprocess.check_output(
        f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{openvpn_ip} "
        f"'ssh -i ~/.ssh/k8s-key.pem -o StrictHostKeyChecking=no ubuntu@{master_private_ip} cat /home/ubuntu/.kube/config'",
        shell=True,
        timeout=30,
        stderr=subprocess.DEVNULL,
    )
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
    """Tạo file kubeconfig tạm 127.0.0.1:6443 để deploy dùng tunnel (trong khi file chính = master IP cho user)."""
    global KUBECONFIG_TUNNEL_FILE
    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    config_tunnel = re.sub(r'server:\s*https://[^\s\n]+', 'server: https://127.0.0.1:6443', config)
    path = os.path.join(_SCRIPT_DIR, ".kube_config_rke2_tunnel.yaml")
    with open(path, "w") as f:
        f.write(config_tunnel)
    os.chmod(path, 0o600)
    KUBECONFIG_TUNNEL_FILE = path


def start_openvpn_port_forward(openvpn_ip, master_private_ip, local_port=6443, remote_port=6443):
    """Starts SSH port forwarding through OpenVPN server: local 6443 -> master:6443."""
    print("--- Step 4.5: Starting SSH Port Forward (OpenVPN -> Master 6443) ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_ENV_DIR, SSH_KEY_FILE_NAME))
    log_file = "/tmp/openvpn-k8s-pf.log"

    try:
        subprocess.run("pkill -f 'ssh.*6443:.*6443' 2>/dev/null || true", shell=True)
        time.sleep(1)
    except Exception:
        pass

    proxy_cmd = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -W %h:%p ubuntu@{openvpn_ip}"
    cmd = (
        f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no "
        f"-o ProxyCommand=\"{proxy_cmd}\" "
        f"-N -L {local_port}:{master_private_ip}:{remote_port} ubuntu@{master_private_ip}"
    )
    with open(log_file, "w") as f:
        proc = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)

    time.sleep(2)
    if proc.poll() is None:
        print(f"  ✓ Port-forward started (PID: {proc.pid})")
        print(f"  ✓ Logs: {log_file}")
        return proc
    print(f"  ⚠ Port-forward may have failed. Check: {log_file}")
    return None


def wait_for_nlb_health_checks():
    print("--- Waiting for NLB to become healthy ---")
    print("  NLB health checks can take 1-2 minutes to pass...")
    print("  This is normal - NLB needs time to register healthy targets...")
    time.sleep(120)  # Tăng thời gian đợi lên 2 phút


def wait_for_k8s_api(kubeconfig_path, max_wait=300):
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    print("  Waiting for Kubernetes API server to be accessible...")
    print("  Note: NLB health checks may take 1-2 minutes to pass...")
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
        
        # Lấy error message
        err = (res.stderr or b"").decode(errors="ignore").strip()
        if err and err != last_error:
            last_error = err
            if waited % 30 == 0:  # Print mỗi 30s
                print(f"  Still waiting... ({err[:150]})")
        
        time.sleep(10)
        waited += 10
    
    print(f"  ⚠ API server not accessible after {max_wait}s")
    if last_error:
        print(f"  Last error: {last_error[:200]}")
    print("  Continuing anyway...")
    return False


def install_ebs_csi_driver():
    """Installs AWS EBS CSI Driver for EBS volume support."""
    print("--- Step 5.6: Installing AWS EBS CSI Driver ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    wait_for_k8s_api(kubeconfig_path, max_wait=300)

    # Create ServiceAccount for EBS CSI controller (required when serviceAccount.create=false)
    print("  Creating ServiceAccount for EBS CSI controller...")
    sa_exists = subprocess.run(
        f"kubectl --kubeconfig={kubeconfig_path} get serviceaccount ebs-csi-controller-sa -n kube-system",
        shell=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if sa_exists.returncode != 0:
        run_command(
            f"kubectl --kubeconfig={kubeconfig_path} create serviceaccount ebs-csi-controller-sa -n kube-system",
            cwd=HELM_DIR,
            env=env,
        )
        print("  ✓ ServiceAccount created")
    else:
        print("  ✓ ServiceAccount already exists")

    print("  Adding AWS EBS CSI Driver Helm repository...")
    run_command("helm repo add aws-ebs-csi-driver https://kubernetes-sigs.github.io/aws-ebs-csi-driver", cwd=HELM_DIR, env=env)
    # Update only the EBS CSI driver repo to avoid timeout issues with other repos
    print("  Updating EBS CSI Driver Helm repository...")
    result = subprocess.run("helm repo update aws-ebs-csi-driver", shell=True, cwd=HELM_DIR, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️  Warning: helm repo update failed (non-critical): {result.stderr}")
        print("  Continuing anyway...")

    print("  Installing AWS EBS CSI Driver...")
    run_command(
        f"helm upgrade --install aws-ebs-csi-driver aws-ebs-csi-driver/aws-ebs-csi-driver "
        f"--namespace kube-system --create-namespace "
        f"--set controller.serviceAccount.create=false "
        f"--set controller.serviceAccount.name=ebs-csi-controller-sa "
        f"--kubeconfig={kubeconfig_path} "
        f"--timeout 10m",
        cwd=HELM_DIR,
        env=env,
    )

    print("  Waiting for EBS CSI Driver pods to be ready...")
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

    if waited >= 300:
        print("  ⚠️  Warning: EBS CSI Driver pods may still be starting. Check with: kubectl get pods -n kube-system | grep ebs-csi")
    else:
        print("  ✓ EBS CSI Driver installed successfully.")

    # Remove default annotation from local-path if it exists (from previous deployments)
    print("  Removing default annotation from local-path storage class (if exists)...")
    result = subprocess.run(
        f"kubectl --kubeconfig={kubeconfig_path} patch storageclass local-path "
        f"-p '{{\"metadata\": {{\"annotations\":{{\"storageclass.kubernetes.io/is-default-class\":\"false\"}}}}}}'",
        shell=True,
        cwd=HELM_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  ✓ Removed default annotation from local-path")
    else:
        # local-path may not exist, which is fine
        print("  ℹ️  local-path storage class not found (this is expected if not installed)")

    # Set EBS as default storage class (will be created when database chart is deployed)
    print("  Note: EBS StorageClass (ebs-sc) will be set as default when database chart is deployed with useEBS: true")


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
    with tempfile.TemporaryDirectory() as td:
        crt = os.path.join(td, "tls.crt")
        key = os.path.join(td, "tls.key")
        run_command(
            f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 "
            f"-keyout {key} -out {crt} -subj \"/CN={RANCHER_HOSTNAME}\"",
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
    run_command(
        f"helm upgrade --install rancher rancher-latest/rancher "
        f"--namespace cattle-system --create-namespace "
        f"--set hostname={RANCHER_HOSTNAME} "
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


def resolve_dns_to_ip(dns_name):
    """Resolves DNS name to IP address."""
    try:
        import socket
        ip = socket.gethostbyname(dns_name)
        print(f"  ✓ Resolved {dns_name} -> {ip}")
        return ip
    except Exception as e:
        print(f"  ⚠ Failed to resolve {dns_name}: {e}")
        return None


# Hostnames cần trỏ ALB: app theo từng env + rancher + argocd
APP_INGRESS_HOST = f"meo-stationery-{TERRAFORM_ENV}.local"
INGRESS_HOSTNAMES = (
    "meo-stationery-dev.local",
    "meo-stationery-staging.local",
    "meo-stationery-prod.local",
    RANCHER_HOSTNAME,
    "argocd.local",
)


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
    """Cập nhật /etc/hosts một dòng cho meo-stationery-{dev,staging,prod}.local, rancher.local, argocd.local (trỏ ALB)."""
    if not alb_dns:
        return False
    print(f"  Using ALB DNS: {alb_dns}")
    ip = resolve_dns_to_ip(alb_dns)
    if not ip:
        print("  ⚠ Cannot resolve ALB, skipping /etc/hosts update")
        return False
    hosts_file = "/etc/hosts"
    entry = f"{ip}\t" + " ".join(INGRESS_HOSTNAMES)
    try:
        result = subprocess.run(f"sudo cat {hosts_file}", shell=True, capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        new_lines = []
        for line in lines:
            if any(h in line for h in INGRESS_HOSTNAMES):
                continue
            new_lines.append(line)
        new_lines.append(entry)
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("\n".join(new_lines) + "\n")
            tmp_path = tmp.name
        subprocess.check_call(f"sudo cp {tmp_path} {hosts_file} && sudo chmod 644 {hosts_file}", shell=True)
        os.unlink(tmp_path)
        print(f"  ✓ /etc/hosts updated: {ip} -> meo-stationery-{{dev,staging,prod}}.local, rancher.local, argocd.local")
        return True
    except subprocess.CalledProcessError:
        _write_setup_hosts_script(alb_dns, ip)
        return False
    except Exception:
        _write_setup_hosts_script(alb_dns, ip)
        return False


def _write_setup_hosts_script(alb_dns, alb_ip):
    """Ghi script để user chạy sudo khi deploy.py không có quyền sửa /etc/hosts."""
    scripts_dir = os.path.join(_SCRIPT_DIR, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    script_path = os.path.join(scripts_dir, "setup-hosts.sh")
    hosts_str = " ".join(INGRESS_HOSTNAMES)
    # sed -E: extended regex so | = OR; escape dots for literal match
    sed_pattern = "|".join(h.replace(".", "\\.") for h in INGRESS_HOSTNAMES)
    content = f"""#!/usr/bin/env bash
# Chạy 1 lần sau ./deploy.py nếu /etc/hosts chưa được cập nhật (sudo): sudo bash {script_path}
set -e
ENTRY="{alb_ip}\t{hosts_str}"
# Xóa dòng cũ có các host này
sudo sed -i.bak -E '/{sed_pattern}/d' /etc/hosts
echo "$ENTRY" | sudo tee -a /etc/hosts
echo "Done. Open: https://meo-stationery-dev.local (dev) | meo-stationery-staging.local (staging) | meo-stationery-prod.local (prod) | rancher.local | argocd.local"
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


def main():
    setup_terraform()
    tf_out = get_terraform_output()

    nlb_dns = tf_out["nlb_dns_name"]["value"]
    openvpn_public_ip = tf_out["openvpn_public_ip"]["value"]
    master_private_ip = tf_out["master_private_ip"]["value"][0]

    print("\n--- RKE2 + OpenVPN ---")
    print(f"  ✓ OpenVPN Server: {openvpn_public_ip}")
    print(f"  ✓ Master Private IP: {master_private_ip}")
    print("  ⏳ Đợi OpenVPN instance SSH sẵn sàng rồi chạy Ansible setup...")

    run_openvpn_ansible(openvpn_public_ip)
    fetch_kubeconfig(openvpn_public_ip, master_private_ip, nlb_dns)
    _create_tunnel_kubeconfig()
    start_openvpn_port_forward(openvpn_public_ip, master_private_ip, local_port=6443, remote_port=6443)
    wait_for_nlb_health_checks()
    install_ebs_csi_driver()

    install_rancher()
    install_argocd()
    deploy_argocd_applications()

    print("\n--- Updating /etc/hosts for Ingress access ---")
    alb_dns = tf_out.get("web_alb_dns_name", {}).get("value", "")
    if alb_dns:
        if not update_etc_hosts_for_alb(alb_dns):
            print("  You can run the script above once to add ALB -> meo-stationery-{dev,staging,prod}.local, rancher.local, argocd.local")
    else:
        print("  ⚠ ALB DNS not available yet, skipping /etc/hosts update")
        print("  You can update manually after ALB is ready")

    start_rancher_portforward()

    # VPN chạy nền: tạo systemd service (project này) để không cần giữ terminal
    _setup_openvpn_systemd_service()

    print("\n" + "=" * 60)
    print("XXX Deployment Complete! XXX")
    print("=" * 60)
    print("\n📋 Cluster (một file kubeconfig, chỉ cần VPN):")
    print(f"   export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"   kubectl get nodes")
    print(f"   ssh -i terraform/environments/{TERRAFORM_ENV}/k8s-key.pem ubuntu@{master_private_ip}")
    print(f"\n🔐 OpenVPN Server: {openvpn_public_ip}")
    print("   SSH qua jump: ssh -i terraform/environments/%s/k8s-key.pem ubuntu@%s" % (TERRAFORM_ENV, openvpn_public_ip))
    if alb_dns:
        print(f"\n🌐 Rancher UI (Ingress via ALB):\n   https://{RANCHER_HOSTNAME}\n   admin / {RANCHER_BOOTSTRAP_PASSWORD}")
        print(f"\n🌐 ArgoCD UI (Ingress via ALB):\n   http://argocd.local")
        print(f"\n🌐 App (Ingress via ALB, env={TERRAFORM_ENV}):\n   https://{APP_INGRESS_HOST}")
    print("\n🌐 Rancher UI (port-forward backup):\n   https://localhost:8443")
    print("\n⚠️  TLS note: self-signed cert → browser warning is expected.")
    print("=" * 60)


if __name__ == "__main__":
    main()
