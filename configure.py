#!/usr/bin/env python3
"""
Phase 2 — CẦN VPN (VPN Required)
==================================
Cài đặt Kubernetes workloads: EBS CSI Driver, Argo CD (management),
External Secrets Operator (dev/prod).

Usage:
    ./configure.py [dev|prod|management]   (mặc định: management)

⚠️  Đảm bảo VPN đang bật trước khi chạy:
    sudo openvpn --config minhtri.ovpn
"""
import glob
import json
import os
import shlex
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

HOSTNAMES_FOR_NLB_BY_ENV = {
    "management": ("argocd.local",),
    "dev": ("meo-stationery-dev.local",),
    "prod": ("meo-stationery-prod.local",),
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


def check_vpn_connectivity():
    """Kiểm tra VPN có đang bật không bằng cách thử kết nối đến private IP."""
    if os.environ.get("SKIP_VPN_CHECK") == "1":
        print("  ⏭ SKIP_VPN_CHECK=1 — bỏ qua kiểm tra VPN.")
        return True

    kubeconfig_path = _kubeconfig_for_deploy()
    if not os.path.isfile(kubeconfig_path):
        print(f"  ✗ Không tìm thấy kubeconfig: {kubeconfig_path}")
        print(f"     Chạy trước: ./provision.py {TERRAFORM_ENV}")
        sys.exit(1)

    print("  Checking VPN connectivity (kubectl get nodes)...")
    try:
        res = subprocess.run(
            f"kubectl --kubeconfig={kubeconfig_path} get nodes --request-timeout=15s",
            shell=True, capture_output=True, timeout=35,
        )
    except subprocess.TimeoutExpired:
        print("  ✗ Timeout — không kết nối được API (VPN chưa bật / route sai / API chậm).")
        print("\n  ⚠️  Bật VPN (vd. sudo openvpn --config sep_tong.ovpn) rồi chạy lại.")
        print("     Hoặc bỏ qua kiểm tra: SKIP_VPN_CHECK=1 ./configure.py", TERRAFORM_ENV)
        sys.exit(1)
    if res.returncode == 0:
        print("  ✓ VPN OK — Kubernetes API is reachable.")
        return True
    else:
        err = (res.stderr or b"").decode(errors="ignore").strip()
        print("  ✗ Không thể kết nối đến Kubernetes API.")
        print(f"     Lỗi: {err[:200]}")
        print("\n  ⚠️  Bật VPN (vd. sudo openvpn --config sep_tong.ovpn) rồi chạy lại.")
        print("     Hoặc bỏ qua kiểm tra: SKIP_VPN_CHECK=1 ./configure.py", TERRAFORM_ENV)
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
    """Thay PLACEHOLDER_MASTER_PRIVATE_IP trong values Git để Helm/Argo đồng bộ (không chỉ --set một lần)."""
    placeholder = "PLACEHOLDER_MASTER_PRIVATE_IP"
    ip = _first_master_private_ip(tf_out)
    if not ip:
        print(f"  ⚠ Bỏ qua patch {placeholder} — không có master_private_ip trong terraform output.")
        return
    for fname in ("cilium-values.yaml", "cilium-values-management.yaml"):
        path = os.path.join(_SCRIPT_DIR, "cilium", fname)
        if not os.path.isfile(path):
            continue
        with open(path, "r") as f:
            content = f.read()
        if placeholder not in content:
            continue
        with open(path, "w") as f:
            f.write(content.replace(placeholder, ip))
        print(f"  ✓ Patched {fname}: {placeholder} → {ip} (k8sServiceHost)")


def install_cilium_via_helm():
    """Cài Cilium (kube-proxy replacement) trước mọi workload cần ClusterIP/DNS — bắt buộc khi RKE2 disable-kube-proxy."""
    print("--- Step 0: Installing Cilium (kube-proxy replacement via Helm) ---")
    kubeconfig_path = _kubeconfig_for_deploy()
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    cilium_dir = os.path.join(_SCRIPT_DIR, "cilium")
    value_files = []
    if TERRAFORM_ENV == "management":
        for name in (
            "cilium-values-management.yaml",
            "cilium-values-management-bootstrap.yaml",
        ):
            p = os.path.join(cilium_dir, name)
            if os.path.isfile(p):
                value_files.append(p)
    elif TERRAFORM_ENV == "dev":
        for name in (
            "cilium-values.yaml",
            "cilium-cluster-dev.yaml",
            "clustermesh-management-peer.yaml",
        ):
            p = os.path.join(cilium_dir, name)
            if os.path.isfile(p):
                value_files.append(p)
    elif TERRAFORM_ENV == "prod":
        for name in (
            "cilium-values.yaml",
            "cilium-cluster-prod.yaml",
            "clustermesh-management-peer.yaml",
        ):
            p = os.path.join(cilium_dir, name)
            if os.path.isfile(p):
                value_files.append(p)

    if not value_files:
        print(f"  ✗ Không tìm thấy file values Cilium trong {cilium_dir}")
        sys.exit(1)

    vf_args = " ".join(f"-f {shlex.quote(p)}" for p in value_files)
    run_command("helm repo add cilium https://helm.cilium.io/", env=env)
    run_command("helm repo update cilium", env=env)
    run_command(
        "helm upgrade --install cilium cilium/cilium "
        f"--version {CILIUM_CHART_VERSION} "
        "--namespace kube-system "
        f"{vf_args} "
        "--wait --timeout 15m",
        env=env,
    )
    # Đảm bảo dataplane sẵn sàng trước CSI/CoreDNS traffic qua Service VIP
    subprocess.run(
        "kubectl rollout status daemonset/cilium -n kube-system --timeout=300s 2>/dev/null || true",
        shell=True,
        env=env,
        capture_output=True,
    )
    print("  ✓ Cilium installed (RKE2 không chạy kube-proxy; Service LB do Cilium).")


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
        "kubectl create namespace external-secrets --dry-run=client -o yaml | kubectl apply -f -",
        env=env,
        timeout=20,
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
            ["kubectl", "apply", "-f", "-"],
            input=yaml_out.stdout, env=env, capture_output=True, text=True, timeout=15,
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
            f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -",
            shell=True, env=env, timeout=10, capture_output=True,
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
        f"-f {values_chart} -f {values_config_base} -f {values_config_env} | kubectl apply -f -"
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
    """
    values_file = os.path.join(_SCRIPT_DIR, "cilium", "cilium-values-management.yaml")
    if not os.path.isfile(values_file):
        return

    print("--- Step 1.5: Patching ClusterMesh management config ---")
    for env_name, placeholder, node_port in [
        ("dev", "PLACEHOLDER_DEV_NODE_IP", "32379"),
        ("prod", "PLACEHOLDER_PROD_NODE_IP", "32380"),
    ]:
        try:
            # Kiểm tra xem folder terraform của env có tồn tại không
            tf_env_dir = os.path.join(TERRAFORM_DIR, "environments", env_name)
            if not os.path.isdir(tf_env_dir):
                continue

            out = subprocess.check_output(
                f"terraform -chdir=environments/{env_name} output -json",
                shell=True, cwd=TERRAFORM_DIR, timeout=15,
            )
            data = json.loads(out)
            # Lấy private IP của worker[0] hoặc master[0]
            # Lưu ý: output master_private_ip trả về một list
            worker_ips = data.get("worker_private_ips", {}).get("value", [])
            master_ips = data.get("master_private_ip", {}).get("value", [])
            node_ip = (worker_ips or master_ips or [None])[0]
            
            if not node_ip:
                print(f"  ⚠ Không lấy được IP của {env_name} cluster, bỏ qua patch.")
                continue
                
            with open(values_file, "r") as f:
                content = f.read()
            
            if placeholder in content:
                content = content.replace(placeholder, node_ip)
                with open(values_file, "w") as f:
                    f.write(content)
                print(f"  ✓ Patched ClusterMesh {env_name}: {placeholder} → {node_ip}:{node_port}")
            else:
                # Nếu placeholder không có (có thể đã patch rồi), thử regex để cập nhật IP mới nếu cần
                # Nhưng tạm thời placeholder là đủ cho lab.
                pass
        except Exception as e:
            # Thường fail nếu terraform env đó chưa init/apply
            pass

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