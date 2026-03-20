#!/bin/bash

# ==============================================================================
# RENDER MANIFESTS SCRIPT
# This script generates pure Kubernetes YAML manifests from the generic Helm chart 
# and external value files, implementing the Rendered Manifests Pattern.
# ==============================================================================

set -e

# Usage helper
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <ENV> <APP_NAME> [VALUES_DIR]"
    echo "Example: $0 dev backend ./values"
    exit 1
fi

ENV=$1
APP_NAME=$2
VALUES_DIR=${3:-"./values"}
MANIFEST_OUT_DIR=".manifest/${ENV}/${APP_NAME}"

# Chart location (single generic chart for all apps)
CHART_DIR="./k8s_helm/generic-app"

echo "=========================================="
echo "Rendering manifests for $APP_NAME in $ENV"
echo "Target Chart: $CHART_DIR"
echo "Values Dir: $VALUES_DIR"
echo "=========================================="

# Create output folder
mkdir -p "$MANIFEST_OUT_DIR"

# Ensure chart exists
if [ ! -d "$CHART_DIR" ]; then
    echo "Error: Chart directory $CHART_DIR not found!"
    exit 1
fi

# Build the helm template command with applicable value files
# Value hierarchy:
#   1) values/app/<app>.yaml
#   2) values/env/<env>/<app>.yaml
CMD="helm template ${ENV}-${APP_NAME} ${CHART_DIR} --set app.name=${APP_NAME}"

BASE_FILE="${VALUES_DIR}/app/${APP_NAME}.yaml"
if [ -f "$BASE_FILE" ]; then
    CMD="$CMD -f $BASE_FILE"
fi

ENV_FILE="${VALUES_DIR}/env/${ENV}/${APP_NAME}.yaml"
if [ -f "$ENV_FILE" ]; then
    CMD="$CMD -f $ENV_FILE"
fi

# Also allow for a direct env file as a fallback
DIRECT_ENV_FILE="${VALUES_DIR}/${APP_NAME}/values-${ENV}.yaml"
if [ -f "$DIRECT_ENV_FILE" ]; then
    CMD="$CMD -f $DIRECT_ENV_FILE"
fi

# Execute Helm and output to manifest
echo "Running: $CMD > ${MANIFEST_OUT_DIR}/manifest.yaml"
eval $CMD > "${MANIFEST_OUT_DIR}/manifest.yaml"

echo "✅ SUCCESS: Raw manifests generated at ${MANIFEST_OUT_DIR}/manifest.yaml"
echo "Commit this YAML file to git. ArgoCD will now sync directly from this directory."
