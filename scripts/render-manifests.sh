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
MANIFEST_OUT_DIR="manifests/${ENV}/${APP_NAME}"

# Chart location (single generic chart for all apps)
CHART_DIR="./k8s_helm/generic-app"

# Determine envType (e.g. non-prod for dev/staging, prod for prod)
if [ "$ENV" == "prod" ]; then
    ENV_TYPE="prod"
else
    ENV_TYPE="non-prod"
fi

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
# The value files hierarchy mirrors the old ArgoCD _app.tpl logic
CMD="helm template ${ENV}-${APP_NAME} ${CHART_DIR} --set app.name=${APP_NAME}"

COMMON_FILE="${VALUES_DIR}/${APP_NAME}/common-values.yaml"
if [ -f "$COMMON_FILE" ]; then
    CMD="$CMD -f $COMMON_FILE"
fi

ENV_TYPE_FILE="${VALUES_DIR}/${APP_NAME}/env-type/${ENV_TYPE}-values.yaml"
if [ -f "$ENV_TYPE_FILE" ]; then
    CMD="$CMD -f $ENV_TYPE_FILE"
fi

APP_VER_FILE="${VALUES_DIR}/${APP_NAME}/app-version/${ENV}-values.yaml"
if [ -f "$APP_VER_FILE" ]; then
    CMD="$CMD -f $APP_VER_FILE"
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
