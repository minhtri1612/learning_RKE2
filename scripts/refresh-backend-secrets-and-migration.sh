#!/usr/bin/env bash
# Force External Secrets to re-fetch app credentials from AWS, then restart the
# backend migration job so it uses the updated DATABASE_URL (e.g. after Terraform
# applied urlencode fix). Run this where kubectl can reach the cluster (e.g. SSH
# to master or via VPN).
# Usage: ./scripts/refresh-backend-secrets-and-migration.sh [dev|staging|prod]

set -e
ENV="${1:-dev}"
NAMESPACE="meo-stationery"
ES_NAME="backend-secrets-${ENV}"
SECRET_NAME="meo-stationery-backend-secrets"
JOB_NAME="meo-station-backend-${ENV}-migration"

echo "=== Refreshing backend secrets and migration (env=$ENV) ==="

# 1. Force External Secrets Operator to reconcile (re-fetch from AWS)
echo "Forcing ExternalSecret $ES_NAME to reconcile..."
kubectl annotate externalsecret "$ES_NAME" -n "$NAMESPACE" \
  reconcile.external-secrets.io/force="$(date +%s)" --overwrite

# 2. Wait for ESO to update the K8s secret (up to 60s)
echo "Waiting for secret $SECRET_NAME to be updated (up to 60s)..."
for i in $(seq 1 12); do
  if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    # Optional: check that DATABASE_URL looks non-empty (has :password@)
    if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.DATABASE_URL}' 2>/dev/null | base64 -d 2>/dev/null | grep -q ':[^@]*@'; then
      echo "Secret updated (DATABASE_URL has password)."
      break
    fi
  fi
  [ "$i" -eq 12 ] && echo "WARN: Timeout waiting for secret; continuing anyway."
  sleep 5
done

# 3. Delete existing secret so next sync is clean (ESO will recreate from AWS)
echo "Deleting K8s secret $SECRET_NAME so ESO recreates it..."
kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE" --ignore-not-found=true

# 4. Wait a few seconds for ESO to recreate the secret
sleep 5

# 5. Delete migration job so ArgoCD/Helm recreates it with new secret
# ArgoCD release name may be "meo-station-backend" or "meo-station-backend-${ENV}", so try both job names
echo "Deleting migration job(s)..."
kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --ignore-not-found=true
kubectl delete job "meo-station-backend-migration" -n "$NAMESPACE" --ignore-not-found=true

echo "Done. ArgoCD will recreate the job; check sync status and migration pod logs."
echo "  kubectl get jobs -n $NAMESPACE"
echo "  kubectl logs -n $NAMESPACE job/<JOB_NAME> -f   # use exact name from get jobs"
