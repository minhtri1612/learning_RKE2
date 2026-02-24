#!/usr/bin/env python3
"""
Phase 2 — CẦN VPN (VPN Required)
==================================
Cài đặt Kubernetes workloads: EBS CSI Driver, ArgoCD (management),
Rancher, External Secrets Operator (dev/prod).

Usage:
    ./configure.py [dev|prod|management]   (mặc định: management)

⚠️  Đảm bảo VPN đang bật trước khi chạy:
    sudo openvpn --config minhtri.ovpn
"""
import json
import os
import re
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
RANCHER_BOOTSTRAP_PASSWORD = "Admin123!"
CERT_MANAGER_CRDS_URL = "https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.crds.yaml"

HOSTNAMES_FOR_ALB_BY_ENV = {
    "management": ("argocd.local",),
    "dev": ("meo-stationery-dev.local", "rancher-dev.local"),
    "prod": ("meo-stationery-prod.local", "rancher-prod.local"),
}


def _get_env():
    if len(sys.argv) >= 2:
        env = sys.argv[1].lower()
        if env in _VALID_ENVS:
            return env
        print(f"Usage: {sys.argv[0]} [dev|prod|management]", file=sys.stderr)
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


def check_vpn_connectivity():
    """Kiểm tra VPN có đang bật không bằng cách thử kết nối đến private IP."""
    kubeconfig_path = _kubeconfig_for_deploy()
    if not os.path.isfile(kubeconfig_path):
        print(f"  ✗ Không tìm thấy kubeconfig: {kubeconfig_path}")
        print(f"     Chạy trước: ./provision.py {TERRAFORM_ENV}")
        sys.exit(1)

    print("  Checking VPN connectivity (kubectl get nodes)...")
    res = subprocess.run(
        f"kubectl --kubeconfig={kubeconfig_path} get nodes --request-timeout=10s",
        shell=True, capture_output=True, timeout=15,
    )
    if res.returncode == 0:
        print("  ✓ VPN OK — Kubernetes API is reachable.")
        return True
    else:
        err = (res.stderr or b"").decode(errors="ignore").strip()
        print("  ✗ Không thể kết nối đến Kubernetes API.")
        print(f"     Lỗi: {err[:200]}")
        print("\n  ⚠️  Hãy bật VPN trước:")
        print("     sudo openvpn --config minhtri.ovpn")
        print(f"\n  Sau đó chạy lại: ./configure.py {TERRAFORM_ENV}")
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
    return True  # Continue anyway


def install_ebs_csi_driver():
    """Installs AWS EBS CSI Driver."""
    print("--- Step 1: Installing AWS EBS CSI Driver ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    run_command(f"kubectl create serviceaccount ebs-csi-controller-sa -n kube-system --dry-run=client -o yaml | kubectl apply -f -", env=env)
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
    for cm in ["argocd-rbac-cm", "argocd-cm"]:
        res = subprocess.run(
            f"kubectl get configmap {cm} -n {namespace} 2>/dev/null",
            shell=True, env=env, capture_output=True,
        )
        if res.returncode == 0:
            subprocess.run(
                f"kubectl delete configmap {cm} -n {namespace} 2>/dev/null",
                shell=True, env=env, capture_output=True,
            )
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

    argocd_values_path = os.path.abspath(os.path.join(_SCRIPT_DIR, "argocd/bootstrap/argocd-install.yaml"))
    run_command(
        f"helm upgrade --install argocd argo/argo-cd "
        f"--namespace argocd --create-namespace "
        f"--values {argocd_values_path} "
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
    projects_dir = os.path.join(_SCRIPT_DIR, "argocd", "projects")
    rbac_dir = os.path.join(_SCRIPT_DIR, "argocd", "rbac")
    if os.path.isdir(projects_dir):
        run_command(f"kubectl apply -f {projects_dir}/", cwd=_SCRIPT_DIR, env=env, timeout=30)
        print("  ✓ ArgoCD Projects applied")
    if os.path.isdir(rbac_dir):
        run_command(f"kubectl apply -f {rbac_dir}/", cwd=_SCRIPT_DIR, env=env, timeout=30)
        print("  ✓ ArgoCD RBAC applied")


def get_rancher_hostname():
    if TERRAFORM_ENV == "management":
        return "rancher.local"
    return f"rancher-{TERRAFORM_ENV}.local"


def ensure_rancher_tls_secret():
    """Create a self-signed TLS secret for Rancher ingress."""
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    exists = subprocess.run(
        "kubectl -n cattle-system get secret tls-rancher-ingress",
        shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if exists.returncode == 0:
        return
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
            env=env, timeout=60,
        )


def install_rancher():
    """Installs Rancher server (dev/prod only)."""
    print("--- Step 2: Installing Rancher ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    run_command(f"kubectl --kubeconfig={kubeconfig_path} apply -f {CERT_MANAGER_CRDS_URL}", env=env, timeout=120)
    run_command("helm repo add rancher-latest https://releases.rancher.com/server-charts/latest", env=env)
    subprocess.run("helm repo update rancher-latest", shell=True, env=env, capture_output=True)
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
        env=env,
    )
    ensure_rancher_tls_secret()
    print("  ✓ Rancher installed.")


def install_external_secrets_operator():
    """Installs External Secrets Operator."""
    print("--- Step 3: Installing External Secrets Operator ---")
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
    crd_name = "clustersecretstores.external-secrets.io"
    for waited in range(0, 120, 5):
        res = subprocess.run(
            f"kubectl get crd {crd_name} --request-timeout=5s 2>/dev/null",
            shell=True, env=env, capture_output=True, timeout=10,
        )
        if res.returncode == 0:
            print(f"  ✓ CRD {crd_name} ready (waited {waited}s).")
            break
        time.sleep(5)


def ensure_aws_secrets_credentials():
    """Tạo K8s Secret aws-secrets-credentials cho ESO."""
    print("--- Step 4: AWS credentials for External Secrets ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    res = subprocess.run(
        "kubectl get secret aws-secrets-credentials -n external-secrets --request-timeout=5s 2>/dev/null",
        shell=True, env=env, capture_output=True, timeout=10,
    )
    if res.returncode == 0:
        print("  ✓ Secret aws-secrets-credentials already exists.")
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
    if access and secret_val:
        yaml_out = subprocess.run(
            ["kubectl", "create", "secret", "generic", "aws-secrets-credentials",
             "-n", "external-secrets",
             "--from-literal=access-key=" + access,
             "--from-literal=secret-access-key=" + secret_val,
             "--dry-run=client", "-o", "yaml"],
            env=env, capture_output=True, text=True, timeout=15,
        )
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=yaml_out.stdout, env=env, capture_output=True, text=True, timeout=15,
        )
        print("  ✓ Created aws-secrets-credentials.")
    else:
        print("  ⚠ Credentials not found. Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY.")


def apply_external_secrets_manifests():
    """Apply ClusterSecretStore + ExternalSecret."""
    print("--- Step 5: Applying External Secrets Manifests ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    # Wait for webhook
    for waited in range(0, 120, 5):
        r = subprocess.run(
            "kubectl get endpoints external-secrets-webhook -n external-secrets "
            "-o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null",
            shell=True, env=env, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            break
        if waited % 15 == 0 and waited > 0:
            print(f"  Waiting for ESO webhook... ({waited}s)")
        time.sleep(5)
    chart_dir = os.path.join(_SCRIPT_DIR, "external-secrets", "applications")
    values_file = os.path.join(chart_dir, f"values-{TERRAFORM_ENV}.yaml")
    if not os.path.isfile(values_file):
        print(f"  ⚠ {values_file} not found, skipping.")
        return
    for ns in ("meo-stationery", "database"):
        subprocess.run(
            f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -",
            shell=True, env=env, timeout=10, capture_output=True,
        )
    run_command(
        f"helm template external-secrets {chart_dir} -f {os.path.join(chart_dir, 'values.yaml')} -f {values_file} | kubectl apply -f -",
        env=env, timeout=30,
    )
    print(f"  ✓ External Secrets applied for {TERRAFORM_ENV}.")


def deploy_argocd_applications():
    """Deploys ArgoCD Bootstrap (Root App → ApplicationSets)."""
    print("--- Step 3: Deploying ArgoCD Bootstrap ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    wait_for_argocd_ready()
    time.sleep(10)
    projects_dir = os.path.join(_SCRIPT_DIR, "argocd", "projects")
    rbac_dir = os.path.join(_SCRIPT_DIR, "argocd", "rbac")
    if os.path.isdir(projects_dir):
        run_command(f"kubectl apply -f {projects_dir}/", env=env, timeout=30)
    if os.path.isdir(rbac_dir):
        run_command(f"kubectl apply -f {rbac_dir}/", env=env, timeout=30)
    root_app = os.path.join(_SCRIPT_DIR, "argocd", "bootstrap", "root-app.yaml")
    if not os.path.isfile(root_app):
        print(f"  ✗ {root_app} not found.")
        sys.exit(1)
    run_command(f"kubectl apply -f {root_app}", env=env, timeout=30)
    print("  ✓ ArgoCD Bootstrap deployed (Root App → ApplicationSets)")
    print("  📌 ApplicationSets will automatically generate Applications for dev + prod")


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


def _write_setup_hosts_script(alb_ip, hostnames):
    scripts_dir = os.path.join(_SCRIPT_DIR, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    script_path = os.path.join(scripts_dir, "setup-hosts.sh")
    hosts_str = " ".join(hostnames)
    sed_pattern = "|".join(h.replace(".", "\\.") for h in hostnames)
    content = f"""#!/usr/bin/env bash\nset -e\nENTRY="{alb_ip}\\t{hosts_str}"\nsudo sed -i.bak -E '/{sed_pattern}/d' /etc/hosts\necho "$ENTRY" | sudo tee -a /etc/hosts\necho "Done: {hosts_str}"\n"""
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    print(f"  ⚠ Run to update /etc/hosts: sudo bash {script_path}")


def update_etc_hosts_for_alb(alb_dns):
    """Cập nhật /etc/hosts với ALB DNS cho env hiện tại."""
    if not alb_dns:
        return False
    hostnames = list(HOSTNAMES_FOR_ALB_BY_ENV.get(TERRAFORM_ENV, ()))
    if not hostnames:
        return False
    ip = resolve_dns_to_ip(alb_dns)
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
def main():
    print("\n" + "=" * 60)
    print(f"  CONFIGURE — Phase 2 (VPN Required) — env: {TERRAFORM_ENV}")
    print("  ⚠️  VPN phải đang bật: sudo openvpn --config minhtri.ovpn")
    print("=" * 60)

    # Guard: check VPN first
    check_vpn_connectivity()

    tf_out = get_terraform_output()
    wait_for_nlb_health_checks()
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
        install_rancher()
        install_external_secrets_operator()
        ensure_aws_secrets_credentials()
        apply_external_secrets_manifests()

    print("\n--- Updating /etc/hosts for Ingress access ---")
    alb_dns = tf_out.get("web_alb_dns_name", {}).get("value", "")
    if alb_dns:
        update_etc_hosts_for_alb(alb_dns)
    else:
        print("  ⚠ ALB DNS not available yet. Run ./scripts/update-hosts.sh later.")

    print("\n" + "=" * 60)
    print("  ✅ CONFIGURE COMPLETE!")
    print("=" * 60)
    print(f"\n  📋 Cluster access (VPN required):")
    print(f"     export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"     kubectl get nodes")
    if TERRAFORM_ENV == "management":
        print(f"\n  🌐 ArgoCD UI:  http://argocd.local")
        print(f"     kubectl port-forward svc/argocd-server -n argocd 8080:443 (backup)")
    else:
        print(f"\n  🌐 Rancher UI: https://rancher-{TERRAFORM_ENV}.local")
        print(f"     App:        https://meo-stationery-{TERRAFORM_ENV}.local")
    print(f"\n  🔧 Update /etc/hosts: ./scripts/update-hosts.sh {TERRAFORM_ENV}")
    print("\n  ⚠️  TLS note: self-signed cert → browser warning is expected.")
    print("=" * 60)


if __name__ == "__main__":
    main()
