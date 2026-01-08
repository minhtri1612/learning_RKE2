#!/usr/bin/env python3
import subprocess
import json
import os
import time
import re
import sys

# Configuration
TERRAFORM_DIR = "./terraform"
ANSIBLE_DIR = "./ansible"
HELM_DIR = "./k8s_helm"
KUBECONFIG_FILE = "kube_config_rke2.yaml"
SSH_KEY_FILE_NAME = "k8s-key.pem"

# Application namespaces / settings
BACKEND_NAMESPACE = "meo-stationery"
DATABASE_NAMESPACE = "database"
RANCHER_HOSTNAME = "rancher.local"
RANCHER_BOOTSTRAP_PASSWORD = "Admin123!"

def run_command(command, cwd=None, env=None):
    """Runs a shell command and raises an exception if it fails."""
    print(f"Running: {command}")
    try:
        subprocess.check_call(command, shell=True, cwd=cwd, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        sys.exit(1)

def get_terraform_output():
    """Gets Terraform output as JSON."""
    print("Fetching Terraform outputs...")
    output = subprocess.check_output("terraform output -json", shell=True, cwd=TERRAFORM_DIR).decode("utf-8")
    return json.loads(output)

def setup_terraform():
    """Applies Terraform configuration."""
    print("--- Step 1: Terraform Apply ---")
    run_command("terraform init", cwd=TERRAFORM_DIR)
    run_command("terraform apply -auto-approve", cwd=TERRAFORM_DIR)

def create_ansible_inventory(tf_output):
    """Creates Ansible inventory file from Terraform outputs."""
    print("--- Step 2: Generating Ansible Inventory ---") 
    master_ips = tf_output["master_public_ip"]["value"]  # Public IPs of master nodes (list)
    worker_ips = tf_output["worker_public_ips"]["value"]  # Public IPs of worker nodes (list)
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME)) #Constructs the absolute path to k8s-key.pem in the terraform directory
    
    inventory_content = "[masters]\n"
    for ip in master_ips:
        inventory_content += f"{ip} ansible_user=ubuntu ansible_ssh_private_key_file={ssh_key_path} ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
    
    inventory_content += "\n[workers]\n"
    for ip in worker_ips:
        inventory_content += f"{ip} ansible_user=ubuntu ansible_ssh_private_key_file={ssh_key_path} ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
    
    inventory_content += "\n[all:children]\nmasters\nworkers\n" #Groups masters and workers together in the inventory file
    
    with open(os.path.join(ANSIBLE_DIR, "inventory.ini"), "w") as f:
        f.write(inventory_content)  # Saves to ansible/inventory.ini
    print("Ansible inventory created.")

# Example output

# [masters]
# 54.123.45.67 ansible_user=ubuntu ansible_ssh_private_key_file=/home/user/terraform/k8s-key.pem ansible_ssh_common_args='-o StrictHostKeyChecking=no'

# [workers]
# 54.123.45.68 ansible_user=ubuntu ansible_ssh_private_key_file=/home/user/terraform/k8s-key.pem ansible_ssh_common_args='-o StrictHostKeyChecking=no'
# 54.123.45.69 ansible_user=ubuntu ansible_ssh_private_key_file=/home/user/terraform/k8s-key.pem ansible_ssh_common_args='-o StrictHostKeyChecking=no'

# [all:children]
# masters
# workers


def update_ansible_playbooks(nlb_dns, master_private_ip):
    """Updates Ansible playbooks with NLB DNS and master private IP."""
    print(f"--- Step 3: Updating Playbooks with NLB DNS: {nlb_dns}, Master IP: {master_private_ip} ---")
    
    # Update init-cluster.yaml
    init_cluster_path = os.path.join(ANSIBLE_DIR, "init-cluster.yaml")
    with open(init_cluster_path, "r") as f:
        data = f.read()
    
    # Regex to find nlb_dns: "..." or nlb_dns: ""
    new_data = re.sub(r'nlb_dns:\s*".*"', f'nlb_dns: "{nlb_dns}"', data)
    new_data = re.sub(r'nlb_dns:\s*""', f'nlb_dns: "{nlb_dns}"', new_data) # Handle empty string case specifically if regex above missed
    
    with open(init_cluster_path, "w") as f:
        f.write(new_data)
        
    # Update worker.yml - use master private IP, not NLB
    worker_path = os.path.join(ANSIBLE_DIR, "worker.yml")
    with open(worker_path, "r") as f:
        data = f.read()
    
    # Update master_ip in worker.yml (handles both placeholder and existing IPs)
    new_data = re.sub(r'master_ip:\s*"[^"]*"', f'master_ip: "{master_private_ip}"', data)
    # Also handle if master_private_ip is None - use a default or skip update
    if master_private_ip is None:
        print("  ⚠ Warning: master_private_ip is None, worker.yml may not be updated correctly")
    
    with open(worker_path, "w") as f:
        f.write(new_data)
    print("Playbooks updated.")

def get_master_private_ip(tf_output):
    """Gets master private IP from Terraform output or inventory."""
    # Try to get from terraform state, or parse from inventory
    try:
        # Get master public IP first
        master_public_ip = tf_output["master_public_ip"]["value"][0]
        # SSH and get private IP
        ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
        cmd = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{master_public_ip} 'hostname -I | awk {{\"print $1\"}}'"
        private_ip = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        return private_ip
    except:
        # Fallback: read from inventory if available
        inventory_path = os.path.join(ANSIBLE_DIR, "inventory.ini")
        if os.path.exists(inventory_path):
            with open(inventory_path, "r") as f:
                for line in f:
                    if line.startswith(master_public_ip):
                        # Try to get from ansible facts later
                        return None
        return None

def run_ansible(tf_output, master_private_ip):
    """Runs Ansible playbooks."""
    print("--- Step 4: Running Ansible Playbooks ---")
    
    # Wait a bit for SSH to be ready
    print("Waiting 30 seconds for instances to fully initialize...")
    time.sleep(30)
    
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    
    # Run all.yaml
    run_command("ansible-playbook -i inventory.ini all.yaml", cwd=ANSIBLE_DIR, env=env)
    
    # Run init-cluster.yaml
    run_command("ansible-playbook -i inventory.ini init-cluster.yaml", cwd=ANSIBLE_DIR, env=env)
    
    # If master_private_ip not provided, get it from master node
    if not master_private_ip:
        master_public_ip = tf_output["master_public_ip"]["value"][0]
        ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
        cmd = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{master_public_ip} 'hostname -I | awk {{\"print $1\"}}'"
        master_private_ip = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        print(f"Detected master private IP: {master_private_ip}")
        # Update worker.yml with detected IP
        worker_path = os.path.join(ANSIBLE_DIR, "worker.yml")
        with open(worker_path, "r") as f:
            data = f.read()
        new_data = re.sub(r'master_ip:\s*"[^"]*"', f'master_ip: "{master_private_ip}"', data)
        with open(worker_path, "w") as f:
            f.write(new_data)
    
    # Run worker.yml
    run_command("ansible-playbook -i inventory.ini worker.yml", cwd=ANSIBLE_DIR, env=env)

def fetch_kubeconfig(master_ip, nlb_dns):
    """Fetches and configures kubeconfig."""
    print("--- Step 5: Fetching Kubeconfig ---")
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
    cmd = f"scp -o StrictHostKeyChecking=no -i {ssh_key_path} ubuntu@{master_ip}:/home/ubuntu/.kube/config ./{KUBECONFIG_FILE}"
    run_command(cmd)
    
    # Replace 127.0.0.1 with NLB DNS
    with open(KUBECONFIG_FILE, "r") as f:
        config = f.read()
    
    config = config.replace("127.0.0.1", nlb_dns)
    config = config.replace("localhost", nlb_dns)
    
    # Disable TLS verification (required because the cert is self-signed and might not cover the NLB DNS yet)
    config = re.sub(r'certificate-authority-data:.*', 'insecure-skip-tls-verify: true', config)
    
    with open(KUBECONFIG_FILE, "w") as f:
        f.write(config)
    
    print(f"Kubeconfig saved to {KUBECONFIG_FILE}")
    # Set permissions
    os.chmod(KUBECONFIG_FILE, 0o600)


def install_storage_class():
    """Installs local-path-provisioner for storage."""
    print("--- Step 5.5: Installing Storage Class ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    # Install local-path-provisioner
    run_command("kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml", cwd=HELM_DIR, env=env)
    
    # Patch it to be default
    run_command("kubectl patch storageclass local-path -p '{\"metadata\": {\"annotations\":{\"storageclass.kubernetes.io/is-default-class\":\"true\"}}}'", cwd=HELM_DIR, env=env)
    
    print("Storage Class installed and set as default.")


def install_cert_manager():
    """Installs cert-manager required by Rancher."""
    print("--- Step 6: Installing cert-manager ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Add / update Jetstack repo and install cert-manager
    run_command("helm repo add jetstack https://charts.jetstack.io", cwd=HELM_DIR, env=env)
    run_command("helm repo update", cwd=HELM_DIR, env=env)
    run_command(
        "helm upgrade --install cert-manager jetstack/cert-manager "
        "--namespace cert-manager "
        "--create-namespace "
        "--set crds.enabled=true",
        cwd=HELM_DIR,
        env=env,
    )


def install_rancher():
    """Installs Rancher server and exposes the UI."""
    print("--- Step 7: Installing Rancher (this may take 5-10 min for image pull) ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Add / update Rancher repo and install Rancher
    run_command("helm repo add rancher-latest https://releases.rancher.com/server-charts/latest", cwd=HELM_DIR, env=env)
    run_command("helm repo update", cwd=HELM_DIR, env=env)
    
    print("  Installing Rancher Helm chart (pulling ~1GB image, please be patient)...")
    print("  You can check progress with: kubectl -n cattle-system get pods -w")
    run_command(
        f"helm upgrade --install rancher rancher-latest/rancher "
        f"--namespace cattle-system "
        f"--create-namespace "
        f"--set hostname={RANCHER_HOSTNAME} "
        f"--set bootstrapPassword={RANCHER_BOOTSTRAP_PASSWORD} "
        f"--timeout 15m",
        cwd=HELM_DIR,
        env=env,
    )
    print("  ✓ Rancher Helm chart installed. Pods may still be starting.")

def install_argocd():
    """Installs ArgoCD for GitOps deployments."""
    print("--- Step 7.5: Installing ArgoCD ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path

    # Add / update ArgoCD repo and install ArgoCD
    run_command("helm repo add argo https://argoproj.github.io/argo-helm", cwd=HELM_DIR, env=env)
    run_command("helm repo update", cwd=HELM_DIR, env=env)
    
    # Get the path to ArgoCD values file
    argocd_values_path = os.path.abspath("./argocd/values-nodeselector.yaml")
    
    print("  Installing ArgoCD Helm chart...")
    run_command(
        f"helm upgrade --install argocd argo/argo-cd "
        f"--namespace argocd "
        f"--create-namespace "
        f"--values {argocd_values_path} "
        f"--timeout 10m",
        cwd=HELM_DIR,
        env=env,
    )
    print("  ✓ ArgoCD Helm chart installed. Pods may still be starting.")

def wait_for_argocd_ready():
    """Waits for ArgoCD server to be ready."""
    print("  Waiting for ArgoCD server to be ready...")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    max_wait = 300  # 5 minutes
    check_interval = 10
    waited = 0
    
    while waited < max_wait:
        try:
            result = subprocess.run(
                "kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-server -o jsonpath='{.items[*].status.containerStatuses[0].ready}'",
                shell=True, env=env, capture_output=True, text=True, timeout=10
            )
            if "true" in result.stdout:
                print(f"  ✓ ArgoCD server is ready (waited {waited}s)")
                return True
        except:
            pass
        
        print(f"  Waiting for ArgoCD server... ({waited}s/{max_wait}s)")
        time.sleep(check_interval)
        waited += check_interval
    
    print(f"  ⚠ ArgoCD not ready after {max_wait}s, proceeding anyway")
    return False

def deploy_argocd_applications():
    """Deploys ArgoCD Application manifests for GitOps."""
    print("--- Step 7.6: Deploying ArgoCD Applications ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    # Wait for ArgoCD to be ready
    wait_for_argocd_ready()
    
    # Give it a bit more time for repo server
    print("  Waiting additional 10 seconds for ArgoCD components...")
    time.sleep(10)
    
    argocd_dir = os.path.abspath("./argocd")
    
    # Apply ArgoCD applications
    print("  Applying backend application...")
    run_command(
        "kubectl apply -f be-application.yaml",
        cwd=argocd_dir,
        env=env,
    )
    
    print("  Applying database application...")
    run_command(
        "kubectl apply -f data-application.yaml",
        cwd=argocd_dir,
        env=env,
    )
    
    print("  ✓ ArgoCD Applications deployed.")
    print("  📝 ArgoCD will automatically sync from Git repository:")
    print("     https://github.com/minhtri1612/learning_RKE2.git")
    print("  💡 To update apps: make changes, commit, and push to Git")

def deploy_helm():
    """Deploys application Helm charts (database + backend)."""
    print("--- Step 8: Deploying Application Helm Charts ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    # Install Database into application namespace
    run_command(
        f"helm upgrade --install postgres ./database "
        f"--namespace {DATABASE_NAMESPACE} "
        f"--create-namespace",
        cwd=HELM_DIR,
        env=env,
    )
    
    # Install Backend into its own namespace
    run_command(
        f"helm upgrade --install backend ./backend "
        f"--namespace {BACKEND_NAMESPACE} "
        f"--create-namespace",
        cwd=HELM_DIR,
        env=env,
    )

def update_etc_hosts(hostname, ip):
    """Automatically adds/updates entry in /etc/hosts."""
    print(f"  Updating /etc/hosts for {hostname} -> {ip}...")
    hosts_file = "/etc/hosts"
    entry = f"{ip}\t{hostname}"
    
    try:
        # Read current /etc/hosts using sudo
        result = subprocess.run(
            f"sudo cat {hosts_file}",
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.splitlines()
        
        # Remove existing entry for this hostname if it exists
        new_lines = []
        found = False
        for line in lines:
            # Skip comments and empty lines
            if line.strip().startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            # Check if this line contains our hostname
            if hostname in line:
                found = True
                # Replace with new entry
                new_lines.append(entry)
            else:
                new_lines.append(line)
        
        # If not found, add at the end
        if not found:
            new_lines.append(entry)
        
        # Write back using sudo
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp.write('\n'.join(new_lines) + '\n')
            tmp_path = tmp.name
        
        # Use sudo to copy temp file to /etc/hosts
        subprocess.check_call(
            f"sudo cp {tmp_path} {hosts_file} && sudo chmod 644 {hosts_file}",
            shell=True
        )
        os.unlink(tmp_path)
        
        print(f"  ✓ Added/updated {hostname} -> {ip} in /etc/hosts")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Failed to update /etc/hosts (may need sudo password): {e}")
        print(f"  Please run manually:")
        print(f"     echo '{entry}' | sudo tee -a /etc/hosts")
        return False
    except Exception as e:
        print(f"  ⚠ Failed to update /etc/hosts: {e}")
        print(f"  Please add manually: {entry}")
        return False

def wait_for_rancher_ready():
    """Waits for at least one Rancher pod to be ready."""
    print("--- Step 8.5: Waiting for Rancher to be ready ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    max_wait = 300  # 5 minutes
    check_interval = 10
    waited = 0
    
    while waited < max_wait:
        try:
            result = subprocess.run(
                "kubectl get pods -n cattle-system -l app=rancher -o jsonpath='{.items[*].status.containerStatuses[0].ready}'",
                shell=True, env=env, capture_output=True, text=True, timeout=10
            )
            if "true" in result.stdout:
                print(f"  ✓ Rancher pod is ready (waited {waited}s)")
                return True
        except:
            pass
        
        print(f"  Waiting for Rancher to be ready... ({waited}s/{max_wait}s)")
        time.sleep(check_interval)
        waited += check_interval
    
    print(f"  ⚠ Rancher not ready after {max_wait}s, proceeding anyway")
    return False

def start_rancher_portforward():
    """Starts port-forward for Rancher UI automatically with retry logic."""
    print("--- Step 9: Starting Rancher Port-Forward ---")
    kubeconfig_path = os.path.abspath(KUBECONFIG_FILE)
    
    # Wait for Rancher to be ready first
    wait_for_rancher_ready()
    
    # Kill any existing port-forward
    try:
        subprocess.check_call("pkill -f 'kubectl port-forward.*rancher'", shell=True, stderr=subprocess.DEVNULL)
        print("  Stopped any existing port-forward")
        time.sleep(2)
    except:
        pass  # No existing port-forward, that's fine
    
    # Start port-forward in background with retry wrapper
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig_path
    
    log_file = "/tmp/rancher-pf.log"
    # Use a wrapper script that retries on failure
    wrapper_script = f'''#!/bin/bash
while true; do
    kubectl port-forward -n cattle-system svc/rancher 8443:443 >> {log_file} 2>&1
    echo "$(date): Port-forward died, restarting in 5 seconds..." >> {log_file}
    sleep 5
done
'''
    
    # Write wrapper script
    wrapper_path = "/tmp/rancher-pf-wrapper.sh"
    with open(wrapper_path, "w") as f:
        f.write(wrapper_script)
    os.chmod(wrapper_path, 0o755)
    
    # Start wrapper in background
    cmd = f"{wrapper_path}"
    process = subprocess.Popen(cmd, shell=True, env=env)
    
    # Wait a moment to check if it started successfully
    time.sleep(5)
    
    # Check if process is still running
    if process.poll() is None:
        print(f"  ✓ Port-forward started successfully (PID: {process.pid})")
        print(f"  ✓ Logs: {log_file}")
        print(f"  ✓ Auto-restart enabled if connection drops")
    else:
        print(f"  ⚠ Port-forward may have failed. Check logs: {log_file}")
        # Try to read error from log
        try:
            with open(log_file, "r") as f:
                error = f.read()
                if error:
                    print(f"  Error: {error[:200]}")
        except:
            pass

def main():
    setup_terraform()
    tf_out = get_terraform_output()
    
    nlb_dns = tf_out["nlb_dns_name"]["value"]
    master_ip = tf_out["master_public_ip"]["value"][0]
    
    create_ansible_inventory(tf_out)
    # Get master private IP
    master_public_ip = tf_out["master_public_ip"]["value"][0]
    ssh_key_path = os.path.abspath(os.path.join(TERRAFORM_DIR, SSH_KEY_FILE_NAME))
    print("Getting master private IP...")
    master_private_ip_cmd = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@{master_public_ip} 'hostname -I | awk {{\"print $1\"}}' 2>/dev/null"
    try:
        master_private_ip = subprocess.check_output(master_private_ip_cmd, shell=True, timeout=15).decode("utf-8").strip()
        print(f"Master private IP: {master_private_ip}")
    except:
        print("Warning: Could not get master private IP, will try during Ansible run")
        master_private_ip = None
    
    update_ansible_playbooks(nlb_dns, master_private_ip)
    run_ansible(tf_out, master_private_ip)
    fetch_kubeconfig(master_ip, nlb_dns)
    install_storage_class()
    install_cert_manager()
    install_rancher()
    install_argocd()
    
    # Deploy via ArgoCD GitOps (requires Git push)
    deploy_argocd_applications()
    
    # Note: Using ArgoCD for GitOps - changes must be pushed to Git
    # Direct Helm deployment (deploy_helm()) is disabled to avoid conflicts
    
    # Update /etc/hosts automatically for ingress access
    print("\n--- Updating /etc/hosts for Ingress access ---")
    update_etc_hosts(RANCHER_HOSTNAME, master_ip)
    update_etc_hosts("meo-stationery.local", master_ip)
    update_etc_hosts("argocd.local", master_ip)
    
    # Optional: Start port-forward as backup (but ingress is preferred)
    start_rancher_portforward()
    
    print("\n" + "="*60)
    print("XXX Deployment Complete! XXX")
    print("="*60)
    print(f"\n📋 Cluster Access:")
    print(f"   export KUBECONFIG={os.path.abspath(KUBECONFIG_FILE)}")
    print(f"\n🌐 Rancher UI (via Ingress - STABLE):")
    print(f"   URL: https://{RANCHER_HOSTNAME}")
    print(f"   Username: admin")
    print(f"   Password: {RANCHER_BOOTSTRAP_PASSWORD}")
    print(f"\n🌐 Rancher UI (via port-forward - backup):")
    print(f"   URL: https://localhost:8443")
    print(f"\n🌐 ArgoCD UI (via Ingress):")
    print(f"   URL: http://argocd.local")
    print(f"   Username: admin")
    print(f"   Password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{{.data.password}}' | base64 -d")
    print(f"   📝 GitOps Repo: https://github.com/minhtri1612/learning_RKE2.git")
    print(f"   💡 Push changes to Git to trigger automatic deployment!")
    print(f"\n🌐 Application (via Ingress):")
    print(f"   URL: http://meo-stationery.local")
    print(f"   (Managed by ArgoCD - syncs from Git)")
    print(f"\n⚠️  Note: You'll see a certificate warning - click 'Advanced' → 'Accept the Risk'")
    print(f"\n💡 Tip: Use Ingress URLs - they're more stable!")
    print("="*60)

if __name__ == "__main__":
    main()
