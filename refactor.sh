#!/bin/bash
set -e

echo "1. Cleaning up old Kustomize patches..."
rm -f config/dev/*.yaml config/prod/*.yaml || true
# Remove the old values directory to start fresh with the new RBAC structure
rm -rf values/* || true

echo "2. Creating correct structural directories..."
mkdir -p values/base/dev
mkdir -p values/base/prod
mkdir -p values/env/base
mkdir -p values/env/dev
mkdir -p values/env/prod

echo "3. Populating Dev-controlled configurations (values/base/)..."
# Dev writes image tags/dev-centric settings here
cat <<EOF > values/base/dev/backend.yaml
workload:
  image:
    tag: "3.0.1"
    pullPolicy: Always
EOF
cat <<EOF > values/base/dev/database.yaml
workload:
  image:
    tag: "13"
    pullPolicy: IfNotPresent
EOF
cat <<EOF > values/base/prod/backend.yaml
workload:
  image:
    tag: "2.0.1"
    pullPolicy: IfNotPresent
EOF
cat <<EOF > values/base/prod/database.yaml
workload:
  image:
    tag: "13"
    pullPolicy: IfNotPresent
EOF

echo "4. Populating Ops-controlled configurations (values/env/)..."
# Ops Baseline
cat <<EOF > values/env/base/backend.yaml
namespace: meo-stationery
migration:
  enabled: false
autoscaling:
  enabled: false
workload:
  image:
    repository: minhtri1612/rke2
ingress:
  enabled: false
EOF

cat <<EOF > values/env/base/database.yaml
# Shared database baseline managed by DevOps.
namespace: database
workload:
  kind: statefulset
  image:
    repository: postgres
initContainer:
  enabled: false
migration:
  enabled: false
autoscaling:
  enabled: false
ingress:
  enabled: false
service:
  type: ClusterIP
  port: 5432
  targetPort: 5432
statefulset:
  containerPort: 5432
  portName: postgres
  volumeName: postgres-storage
  mountPath: /var/lib/postgresql/data
  subPath: pgdata
  pgdataPath: /var/lib/postgresql/data/pgdata
livenessProbe:
  enabled: true
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6
  successThreshold: 1
replicas: 1
persistence:
  useEBS: false
auth:
  username: meo_admin
  database: meo_stationery
EOF

# Ops Dev Overrides
cat <<EOF > values/env/dev/backend.yaml
replicaCount: 3
ingress:
  enabled: true
  host: meo-stationery-dev.local
databaseConnection:
  host: dev-database-generic-app.database.svc.cluster.local
autoscaling:
  enabled: true
  minReplicas: 5
  maxReplicas: 8
existingSecret:
  name: meo-stationery-backend-secrets-dev
EOF

cat <<EOF > values/env/dev/database.yaml
existingSecret:
  name: meo-stationery-database-secrets-dev
EOF

# Ops Prod Overrides
cat <<EOF > values/env/prod/backend.yaml
replicaCount: 10
ingress:
  enabled: true
  host: meo-stationery-prod.local
databaseConnection:
  host: prod-database-generic-app.database.svc.cluster.local
workload:
  resources:
    requests:
      memory: "512Mi"
      cpu: "250m"
    limits:
      memory: "2Gi"
      cpu: "1000m"
autoscaling:
  enabled: true
  minReplicas: 10
  maxReplicas: 15
networkPolicy:
  enabled: true
existingSecret:
  name: meo-stationery-backend-secrets
EOF

cat <<EOF > values/env/prod/database.yaml
persistence:
  size: 10Gi
  provisionStorageClass: false
existingSecret:
  name: meo-stationery-database-secrets
EOF

echo "5. Writing the pure Kustomization Orchestrators..."
cat <<EOF > config/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

helmCharts:
  - name: generic-app
    releaseName: dev-backend
    path: ../../k8s_helm/generic-app
    valuesInline:
      app:
        name: backend
    valuesFiles:
      - ../../values/env/base/backend.yaml
      - ../../values/env/dev/backend.yaml
      - ../../values/base/dev/backend.yaml

  - name: generic-app
    releaseName: dev-database
    path: ../../k8s_helm/generic-app
    valuesInline:
      app:
        name: database
    valuesFiles:
      - ../../values/env/base/database.yaml
      - ../../values/env/dev/database.yaml
      - ../../values/base/dev/database.yaml
EOF

cat <<EOF > config/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

helmCharts:
  - name: generic-app
    releaseName: prod-backend
    path: ../../k8s_helm/generic-app
    valuesInline:
      app:
        name: backend
    valuesFiles:
      - ../../values/env/base/backend.yaml
      - ../../values/env/prod/backend.yaml
      - ../../values/base/prod/backend.yaml

  - name: generic-app
    releaseName: prod-database
    path: ../../k8s_helm/generic-app
    valuesInline:
      app:
        name: database
    valuesFiles:
      - ../../values/env/base/database.yaml
      - ../../values/env/prod/database.yaml
      - ../../values/base/prod/database.yaml
EOF

echo "Refactoring Complete!"
