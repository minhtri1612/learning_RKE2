#!/bin/bash

echo "=== XUẤT RA THƯ MỤC .MANIFEST ==="
mkdir -p ./.manifest/dev/
mkdir -p ./.manifest/prod/

# DEV Environment (Sinh ra CẢ Backend lẫn Database cùng 1 lúc!)
echo "Rendering DEV..."
kubectl kustomize --enable-helm ./config/dev > ./.manifest/dev/manifest.yaml

# PROD Environment (Sinh ra CẢ Backend lẫn Database cùng 1 lúc!)
echo "Rendering PROD..."
kubectl kustomize --enable-helm ./config/prod > ./.manifest/prod/manifest.yaml

echo "Done! Hãy kiểm tra ./.manifest/dev/manifest.yaml và ./.manifest/prod/manifest.yaml"
