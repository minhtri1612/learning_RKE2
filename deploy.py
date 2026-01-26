#!/usr/bin/env python3
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time

# Configuration
TERRAFORM_DIR = "./terraform"
ANSIBLE_DIR = "./ansible"
HELM_DIR = "./k8s_helm"
KUBECONFIG_FILE = "kube_config_rke2.yaml"
SSH_KEY_FILE_NAME = "k8s-key.pem"

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
    """Gets Terraform output as JSON."""
    print("Fetching Terraform outputs...")
    output = subprocess.check_output("terraform output -json", shell=True, cwd=TERRAFORM_DIR).decode("utf-8")
    return json.loads(output)


def setup_terraform():
    """Applies Terraform configuration."""
    print("--- Step 1: Terraform Apply ---")
    run_command("terraform init -input=false", cwd=TERRAFORM_DIR)
    run_command("terraform apply -auto-approve -input=false", cwd=TERRAFORM_DIR)


def _ensure_python_deps_for_dynamic_inventory():
    """Ensure boto3/botocore exist so Ansible aws_ec2 inventory plugin works."""
    print("  Checking Python dependencies (boto3, botocore)...")
    try:
        res = subprocess.run([sys.executable, "-c", "import boto3, botocore"], capture_output=True, timeout=5)
        if res.returncode == 0:
            print("  ✓ boto3 and botocore already installed")
            return
    except Exception:
        pass

    print("  ⚠ Installing boto3/botocore (required for AWS EC2 inventory plugin)...")
    install_methods = [
        ([sys.executable, "-m", "pip", "install", "--user", "boto3", "botocore"], "pip --user"),
        ([sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "boto3", "botocore"], "pip --user --break-system-packages"),
        (["sudo", "-n", "apt", "install", "-y", "python3-boto3"], "apt python3-boto3 (non-interactive)"),
        (["pip3", "install", "--user", "--break-system-packages", "boto3", "botocore"], "pip3 --user --break-system-packages"),
    ]

    for cmd, name in install_methods:
        try:
            print(f"  Attempting installation: {name}")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                continue
            verify = subprocess.run([sys.executable, "-c", "import boto3, botocore"], capture_output=True, timeout=5)
            if verify.returncode == 0:
                print(f"  ✓ boto3/botocore installed ({name})")
                return
        except Exception:
            continue

    print("  ✗ Could not auto-install boto3/botocore.")
    print("    Try one of:")
    print("    - pip3 install --user --break-system-packages boto3 botocore")
    print("    - sudo apt install -y python3-boto3")
    raise RuntimeError("Missing boto3/botocore")


def setup_ansible_dynamic_inventory():
    """Sets up Ansible to use AWS EC2 dynamic inventory (no hardcoded IPs!)."""
    print("--- Step 2: Setting up AWS EC2 Dynamic Inventory ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))

    _ensure_python_deps_for_dynamic_inventory()

    # Ensure amazon.aws collection exists
    try:
        result = subprocess.run("ansible-galaxy collection list amazon.aws", shell=True, capture_output=True, text=True)
        if "amazon.aws" not in result.stdout:
            print("  ⚠ Installing AWS collection for Ansible...")
            run_command("ansible-galaxy collection install amazon.aws", cwd=ANSIBLE_DIR)
            print("  ✓ AWS collection installed")
        else:
            print("  ✓ AWS collection already installed")
    except Exception:
        print("  ⚠ Installing AWS collection for Ansible...")
        run_command("ansible-galaxy collection install amazon.aws", cwd=ANSIBLE_DIR)

    # Update inventory_aws_ec2.yml with absolute SSH key path
    inventory_yml_path = os.path.join(ANSIBLE_DIR, "inventory_aws_ec2.yml")
    with open(inventory_yml_path, "r") as f:
        content = f.read()
    content = re.sub(r'ansible_ssh_private_key_file:\s*"[^"]*"', f'ansible_ssh_private_key_file: "{ssh_key_path}"', content)
    with open(inventory_yml_path, "w") as f:
        f.write(content)

    # Update ansible.cfg if present (fallback)
    ansible_cfg_path = os.path.join(ANSIBLE_DIR, "ansible.cfg")
    if os.path.exists(ansible_cfg_path):
        with open(ansible_cfg_path, "r") as f:
            cfg = f.read()
        cfg = re.sub(r"private_key_file\s*=\s*.*", f"private_key_file = {ssh_key_path}", cfg)
        with open(ansible_cfg_path, "w") as f:
            f.write(cfg)

    # Verify AWS credentials are available (non-fatal)
    try:
        subprocess.check_call("aws sts get-caller-identity", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  ✓ AWS credentials verified")
    except Exception:
        print("  ⚠ Warning: AWS credentials not found. Make sure AWS CLI is configured (aws configure).")

    print("  ✓ Using AWS EC2 dynamic inventory (inventory_aws_ec2.yml)")
    print("    - k8s-master-* -> masters group")
    print("    - k8s-worker-* -> workers group")
    print("    - NO hardcoded IPs")

    # Best-effort demo
    try:
        res = subprocess.run(
            f"ansible-inventory -i {inventory_yml_path} --list",
            shell=True,
            cwd=ANSIBLE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0:
            inv = json.loads(res.stdout)
            masters = inv.get("masters", {}).get("hosts", [])
            workers = inv.get("workers", {}).get("hosts", [])
            print(f"  ✓ Discovered {len(masters)} master(s): {masters}")
            print(f"  ✓ Discovered {len(workers)} worker(s): {workers}")
    except Exception:
        pass


def update_ansible_playbooks(nlb_dns, master_private_ip):
    """Updates Ansible playbooks with NLB DNS and master private IP."""
    print(f"--- Step 3: Updating Playbooks (NLB: {nlb_dns}, Master private IP: {master_private_ip}) ---")

    init_cluster_path = os.path.join(ANSIBLE_DIR, "init-cluster.yaml")
    with open(init_cluster_path, "r") as f:
        data = f.read()
    data = re.sub(r'nlb_dns:\s*".*"', f'nlb_dns: "{nlb_dns}"', data)
    data = re.sub(r'nlb_dns:\s*""', f'nlb_dns: "{nlb_dns}"', data)
    with open(init_cluster_path, "w") as f:
        f.write(data)

    if master_private_ip:
        worker_path = os.path.join(ANSIBLE_DIR, "worker.yml")
        with open(worker_path, "r") as f:
            w = f.read()
        w = re.sub(r'master_ip:\s*"[^"]*"', f'master_ip: "{master_private_ip}"', w)
        with open(worker_path, "w") as f:
            f.write(w)


def _get_master_private_ip_via_ssh(master_public_ip):
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
    cmd = (
        f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=10 "
        f"ubuntu@{master_public_ip} 'hostname -I | awk {{\"print $1\"}}' 2>/dev/null"
    )
    try:
        return subprocess.check_output(cmd, shell=True, timeout=15).decode("utf-8").strip()
    except Exception:
        return None


def _fetch_existing_rke2_token(tf_output):
    """
    Best-effort: fetch the currently configured token from the master node.
    This avoids changing the join token on reruns.
    Returns token string or None.
    """
    try:
        master_public_ip = tf_output["master_public_ip"]["value"][0]
        if not master_public_ip:
            return None
    except Exception:
        return None

    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
    base_ssh = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{master_public_ip}"

    # Prefer explicit token in config.yaml
    try:
        out = subprocess.check_output(
            base_ssh
            + " \"sudo sed -n 's/^token:[[:space:]]*//p' /etc/rancher/rke2/config.yaml 2>/dev/null | head -n1\"",
            shell=True,
            timeout=15,
        ).decode("utf-8", errors="ignore").strip()
        if out:
            return out.strip().strip('"').strip("'")
    except Exception:
        pass

    # Fallback: node-token (exists after server init; valid for joins)
    try:
        out = subprocess.check_output(
            base_ssh + " \"sudo cat /var/lib/rancher/rke2/server/node-token 2>/dev/null | head -n1\"",
            shell=True,
            timeout=15,
        ).decode("utf-8", errors="ignore").strip()
        if out:
            return out
    except Exception:
        pass

    return None


def _ensure_ansible_vault_ready(tf_output, vault_pass_file, vault_pass_file_relative):
    """
    Make Ansible Vault non-interactive and self-healing:
    - Ensure ansible/.vault_pass exists (create random if missing)
    - If vars/secrets.yml can't be decrypted with current pass, recreate+encrypt it.
    """
    secrets_path = os.path.join(ANSIBLE_DIR, "vars", "secrets.yml")

    # Ensure vault pass exists
    if not os.path.exists(vault_pass_file):
        os.makedirs(os.path.dirname(vault_pass_file), exist_ok=True)
        with open(vault_pass_file, "w") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
        os.chmod(vault_pass_file, 0o600)
        print(f"  ✓ Created vault password file: {vault_pass_file}")

    def _write_plain_secrets():
        token = _fetch_existing_rke2_token(tf_output)
        if not token:
            token = secrets.token_urlsafe(24)
        os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
        with open(secrets_path, "w") as f:
            f.write(f'rke2_token: "{token}"\n')
        os.chmod(secrets_path, 0o600)

    # If secrets file missing, create plaintext then encrypt
    if not os.path.exists(secrets_path):
        _write_plain_secrets()

    # If secrets.yml is not vault-encrypted, nothing to do
    try:
        with open(secrets_path, "r") as f:
            first = (f.readline() or "").strip()
        if not first.startswith("$ANSIBLE_VAULT;"):
            return
    except Exception:
        return

    # Test decrypt (quiet). If fail -> wrong password, recreate+encrypt.
    test = subprocess.run(
        f"ansible-vault view vars/secrets.yml --vault-password-file {vault_pass_file_relative}",
        shell=True,
        cwd=ANSIBLE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if test.returncode == 0:
        return

    print("  ⚠ Vault decrypt failed for ansible/vars/secrets.yml.")
    print("  Auto-resetting vault password and re-encrypting secrets.yml...")

    # Rotate password
    with open(vault_pass_file, "w") as f:
        f.write(secrets.token_urlsafe(32) + "\n")
    os.chmod(vault_pass_file, 0o600)

    # Recreate secrets.yml plaintext then encrypt with the new password
    _write_plain_secrets()
    run_command(
        f"ansible-vault encrypt vars/secrets.yml --vault-password-file {vault_pass_file_relative}",
        cwd=ANSIBLE_DIR,
    )
    print("  ✓ secrets.yml re-encrypted with new vault password")


def run_ansible(tf_output, master_private_ip):
    """Runs Ansible playbooks using dynamic inventory."""
    print("--- Step 4: Running Ansible Playbooks ---")
    print("Waiting 30 seconds for instances to fully initialize...")
    time.sleep(30)

    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    inventory_file = "inventory_aws_ec2.yml"
    vault_pass_file = os.path.join(ANSIBLE_DIR, ".vault_pass")
    vault_pass_file_relative = ".vault_pass"  # correct when cwd=ANSIBLE_DIR

    _ensure_ansible_vault_ready(tf_output, vault_pass_file, vault_pass_file_relative)

    # IMPORTANT: ansible-playbook is run with cwd=ANSIBLE_DIR, so pass a relative path
    # to avoid resolving to ansible/ansible/.vault_pass.
    vault_flag = f"--vault-password-file={vault_pass_file_relative}" if os.path.exists(vault_pass_file) else ""

    run_command(f"ansible-playbook -i {inventory_file} {vault_flag} all.yaml", cwd=ANSIBLE_DIR, env=env)
    run_command(f"ansible-playbook -i {inventory_file} {vault_flag} init-cluster.yaml", cwd=ANSIBLE_DIR, env=env)

    if not master_private_ip:
        cmd = f"ansible masters -i {inventory_file} -m setup -a 'filter=ansible_default_ipv4' --one-line"
        try:
            out = subprocess.check_output(cmd, shell=True, cwd=ANSIBLE_DIR, env=env, stderr=subprocess.DEVNULL).decode("utf-8")
            m = re.search(r'"address":\s*"([^"]+)"', out)
            if m:
                master_private_ip = m.group(1)
        except Exception:
            pass

        if not master_private_ip:
            master_public_ip = tf_output["master_public_ip"]["value"][0]
            master_private_ip = _get_master_private_ip_via_ssh(master_public_ip)

        if master_private_ip:
            worker_path = os.path.join(ANSIBLE_DIR, "worker.yml")
            with open(worker_path, "r") as f:
                w = f.read()
            w = re.sub(r'master_ip:\s*"[^"]*"', f'master_ip: "{master_private_ip}"', w)
            with open(worker_path, "w") as f:
                f.write(w)
            print(f"  ✓ Detected master private IP: {master_private_ip}")
        else:
            print("  ⚠ Could not detect master private IP; worker join may fail.")

    run_command(f"ansible-playbook -i {inventory_file} {vault_flag} worker.yml", cwd=ANSIBLE_DIR, env=env)


def fetch_kubeconfig(master_ip, nlb_dns):
    """Fetches and configures kubeconfig."""
    print("--- Step 5: Fetching Kubeconfig ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))

    print("  Waiting for RKE2 to generate kubeconfig...")
    for waited in range(0, 121, 5):
        try:
            res = subprocess.run(
                f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@{master_ip} "
                f"'test -f /home/ubuntu/.kube/config && echo exists'",
                shell=True,
                capture_output=True,
                timeout=10,
            )
            if res.returncode == 0 and b"exists" in res.stdout:
                print(f"  ✓ kubeconfig file found (waited {waited}s)")
                break
        except Exception:
            pass
        time.sleep(5)

    run_command(f"scp -o StrictHostKeyChecking=no -i {ssh_key_path} ubuntu@{master_ip}:/home/ubuntu/.kube/config ./{KUBECONFIG_FILE}")

    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    config = config.replace("127.0.0.1", nlb_dns).replace("localhost", nlb_dns)
    config = re.sub(r"certificate-authority-data:.*", "insecure-skip-tls-verify: true", config)
    with open(KUBECONFIG_FILE, "w") as f:
        f.write(config)
    os.chmod(KUBECONFIG_FILE, 0o600)
    print(f"  ✓ Kubeconfig saved to {KUBECONFIG_FILE}")


def wait_for_nlb_health_checks():
    print("--- Waiting for NLB to become healthy ---")
    print("  NLB health checks can take 1-2 minutes to pass...")
    time.sleep(90)


def wait_for_k8s_api(kubeconfig_path, max_wait=300):
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    print("  Waiting for Kubernetes API server to be accessible...")
    waited = 0
    while waited < max_wait:
        res = subprocess.run(
            f"kubectl --kubeconfig={kubeconfig_path} get nodes --request-timeout=10s",
            shell=True,
            capture_output=True,
            env=env,
            timeout=20,
        )
        if res.returncode == 0:
            print(f"  ✓ API server is accessible (waited {waited}s)")
            return True
        if waited % 30 == 0:
            err = (res.stderr or b"").decode(errors="ignore").strip()
            if err:
                print(f"  Still waiting... ({err[:120]})")
        time.sleep(10)
        waited += 10
    print(f"  ⚠ API server not accessible after {max_wait}s (continuing anyway)")
    return False


def install_ebs_csi_driver():
    """Installs AWS EBS CSI Driver for EBS volume support."""
    print("--- Step 5.6: Installing AWS EBS CSI Driver ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    wait_for_argocd_ready()
    print("  Waiting additional 10 seconds for ArgoCD components...")
    time.sleep(10)

    argocd_dir = os.path.abspath("./argocd")
    run_command("kubectl apply -f be-application.yaml", cwd=argocd_dir, env=env)
    run_command("kubectl apply -f data-application.yaml", cwd=argocd_dir, env=env)
    print("  ✓ ArgoCD Applications deployed.")
    print("  📝 GitOps Repo: https://github.com/minhtri1612/learning_RKE2.git")


def update_etc_hosts(hostname, ip):
    """Automatically adds/updates entry in /etc/hosts (requires sudo)."""
    print(f"  Updating /etc/hosts for {hostname} -> {ip}...")
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
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Failed to update /etc/hosts (may need sudo password): {e}")
        print(f"  Please run manually:\n     echo '{entry}' | sudo tee -a /etc/hosts")
        return False
    except Exception as e:
        print(f"  ⚠ Failed to update /etc/hosts: {e}")
        return False


def wait_for_rancher_ready():
    """Waits for at least one Rancher pod to be ready."""
    print("--- Step 8.5: Waiting for Rancher to be ready ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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


def start_rancher_portforward():
    """Starts port-forward for Rancher UI automatically with retry logic."""
    print("--- Step 9: Starting Rancher Port-Forward ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
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
    master_ip = tf_out["master_public_ip"]["value"][0]

    setup_ansible_dynamic_inventory()

    master_private_ip = _get_master_private_ip_via_ssh(master_ip)
    if master_private_ip:
        print(f"Master private IP: {master_private_ip}")
    else:
        print("Warning: Could not get master private IP yet; will try during Ansible run")

    update_ansible_playbooks(nlb_dns, master_private_ip)
    run_ansible(tf_out, master_private_ip)

    fetch_kubeconfig(master_ip, nlb_dns)
    wait_for_nlb_health_checks()
    install_ebs_csi_driver()

    install_rancher()
    install_argocd()
    deploy_argocd_applications()

    print("\n--- Updating /etc/hosts for Ingress access ---")
    update_etc_hosts(RANCHER_HOSTNAME, master_ip)
    update_etc_hosts("meo-stationery.local", master_ip)
    update_etc_hosts("argocd.local", master_ip)

    start_rancher_portforward()

    print("\n" + "=" * 60)
    print("XXX Deployment Complete! XXX")
    print("=" * 60)
    print(f"\n📋 Cluster Access:\n   export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"\n🌐 Rancher UI (Ingress):\n   https://{RANCHER_HOSTNAME}\n   admin / {RANCHER_BOOTSTRAP_PASSWORD}")
    print("\n🌐 Rancher UI (port-forward backup):\n   https://localhost:8443")
    print("\n🌐 ArgoCD UI (Ingress):\n   http://argocd.local\n   admin / (run: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)")
    print("\n🌐 App (Ingress):\n   http://meo-stationery.local")
    print("\n⚠️  TLS note: self-signed cert → browser warning is expected.")
    print("=" * 60)


if __name__ == "__main__":
    main()
