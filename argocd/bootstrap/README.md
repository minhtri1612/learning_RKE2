# ArgoCD Management Control Plane - Production Layout

This directory manages the ArgoCD instance and its associated governance structures for a Hub-and-Spoke Kubernetes architecture.

## 🚀 Bootstrap Sequence

To initialize the management cluster, apply manifests in the following order:

1.  **Namespace**: `kubectl apply -f argocd/bootstrap/00-namespace.yaml`
2.  **ArgoCD Core**: Ensure ArgoCD is installed via `configure.py` (which uses `01-argocd-install.yaml`).
3.  **Root Control Plane**: `kubectl apply -f argocd/bootstrap/02-root-app.yaml`

Once the Root Application is applied, it will automatically synchronize all other management components (Projects, Clusters, Repositories, etc.) via GitOps.

## 📁 Directory Roles

- `bootstrap/`: Sequential manifests for cluster initialization.
- `projects/`: Multi-tenant isolation (dev, staging, prod, infrastructure).
- `appsets/`: Templates for automated application discovery across all clusters.
- `clusters/`: Registration secrets for external clusters (Dev/Prod).
- `repositories/`: Git repository credentials and SSH known-hosts.
- `config/`: Global ArgoCD parameters (non-sensitive).
- `notifications/`: Slack/Email alerting configurations.
- `image-updater/`: Automated container image update policies.

## 🔧 Adding New Services

To add a new microservice to the system:
1.  Create a folder in `k8s_helm/` with your Helm chart.
2.  Add a `config.json` file in that folder (set `namespace`, `version`, `syncWave`, `helmPath`).
3.  Push to Git. The `root-appsets` (ApplicationSet) will detect the new directory and create the App automatically.

---
**Note on Security**: Never commit plain-text passwords to `repositories/` or `clusters/`. Use placeholder-based manifests and fill them manually OR use `ExternalSecrets` to pull from AWS Secrets Manager.
