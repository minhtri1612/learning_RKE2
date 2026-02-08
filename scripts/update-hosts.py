#!/usr/bin/env python3
"""
Script để tự động cập nhật /etc/hosts với ALB DNS cho các environment.
Sử dụng: python scripts/update-hosts.py [dev|prod|management]
"""

import json
import os
import re
import socket
import subprocess
import sys

def get_terraform_output(env):
    """Get terraform output for specific environment."""
    try:
        cmd = f"terraform -chdir=terraform/environments/{env} output -json"
        output = subprocess.check_output(cmd, shell=True).decode("utf-8")
        return json.loads(output)
    except Exception as e:
        print(f"Error getting terraform output for {env}: {e}")
        return {}

def resolve_alb_ip(alb_dns):
    """Resolve ALB DNS to IP address."""
    try:
        return socket.gethostbyname(alb_dns)
    except socket.gaierror as e:
        print(f"Failed to resolve {alb_dns}: {e}")
        return None

def get_hostnames_for_env(env):
    """Get ingress hostnames for environment."""
    if env == "management":
        return ["argocd.local", "rancher.local"]
    elif env == "dev":
        return ["meo-stationery-dev.local"]
    elif env == "prod":
        return ["meo-stationery-prod.local", "rancher.local"]
    else:
        return []

def update_hosts_file(env):
    """Update /etc/hosts with ALB entries for environment."""
    print(f"=== Updating /etc/hosts for {env} environment ===")
    
    # Get terraform outputs
    tf_outputs = get_terraform_output(env)
    alb_dns = tf_outputs.get("web_alb_dns_name", {}).get("value", "")
    
    if not alb_dns:
        print(f"No ALB DNS found for {env} environment")
        return False
        
    # Resolve ALB to IP
    print(f"Resolving ALB DNS: {alb_dns}")
    alb_ip = resolve_alb_ip(alb_dns)
    if not alb_ip:
        return False
        
    print(f"ALB IP: {alb_ip}")
    
    # Get hostnames for this environment
    hostnames = get_hostnames_for_env(env)
    if not hostnames:
        print(f"No hostnames defined for {env} environment")
        return False
        
    # Read current /etc/hosts
    hosts_file = "/etc/hosts"
    try:
        with open(hosts_file, "r") as f:
            hosts_content = f.read()
    except PermissionError:
        print(f"Need sudo to read {hosts_file}")
        return False
        
    # Check and prepare entries
    new_entries = []
    for hostname in hostnames:
        if hostname in hosts_content:
            # Check if it points to correct IP
            pattern = rf"^(\S+)\s+.*{re.escape(hostname)}"
            match = re.search(pattern, hosts_content, re.MULTILINE)
            if match and match.group(1) != alb_ip:
                print(f"⚠️  {hostname} exists but points to {match.group(1)}, should be {alb_ip}")
                print(f"Manual update: sudo sed -i 's/{match.group(1)}.*{hostname}.*/{alb_ip} {hostname}/' {hosts_file}")
            elif match:
                print(f"✓ {hostname} already points to {alb_ip}")
            else:
                print(f"⚠️  {hostname} exists in /etc/hosts but format unclear")
        else:
            new_entries.append(f"{alb_ip} {hostname}")
            
    if new_entries:
        print(f"Adding entries to {hosts_file}:")
        for entry in new_entries:
            print(f"  {entry}")
            
        try:
            with open(hosts_file, "a") as f:
                f.write(f"\n# Added by update-hosts.py for {env}\n")
                for entry in new_entries:
                    f.write(f"{entry}\n")
            print(f"✓ Updated {hosts_file}")
            return True
        except PermissionError:
            print(f"Need sudo to write to {hosts_file}. Run manually:")
            print(f"echo '# Added by update-hosts.py for {env}' | sudo tee -a {hosts_file}")
            for entry in new_entries:
                print(f"echo '{entry}' | sudo tee -a {hosts_file}")
            return False
    else:
        print("✓ /etc/hosts already up to date")
        return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/update-hosts.py [dev|prod|management|all]")
        sys.exit(1)
        
    env = sys.argv[1].lower()
    
    if env == "all":
        environments = ["management", "dev", "prod"]
        success = True
        for e in environments:
            if not update_hosts_file(e):
                success = False
            print()
        sys.exit(0 if success else 1)
    elif env in ["dev", "prod", "management"]:
        success = update_hosts_file(env)
        sys.exit(0 if success else 1)
    else:
        print("Invalid environment. Use: dev, prod, management, or all")
        sys.exit(1)

if __name__ == "__main__":
    main()