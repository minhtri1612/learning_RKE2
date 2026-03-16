{{/*
─── CHUNG TEMPLATE ───
Sinh 1 ArgoCD Application cho bất kỳ component nào trong stack.

Naming convention:
  parent stack : <env>-<project>-stack   (bootstrap tự đặt)
  child apps   : <env>-<name>-app        (template này sinh ra)

Phân loại theo category (labels):
  project     : tên project (vd: meostation)
  env         : môi trường (dev / prod)
  version     : version đang pin (targetRevision)

Usage:
  {{- include "stacks.application" (dict "name" "backend" "root" $) }}
  {{- include "stacks.application" (dict "name" "database" "root" $) }}

Flow values cho k8s resources:
  1. k8s_helm/<name>/values.yaml          ← base defaults
  2. k8s_helm/<name>/values-<env>.yaml    ← env overrides (replicas, secrets, ingress...)
  3. inline values (nếu có)               ← image tag override (backend only)
*/}}
{{- define "stacks.application" -}}
{{- $name      := .name -}}
{{- $root      := .root -}}
{{- $app       := index $root.Values.apps $name -}}
{{- $env       := $root.Values.env -}}
{{- $project   := $root.Values.name -}}
{{- $svc       := index ($root.Values.services | default dict) $name | default dict -}}
{{- $targetRev := $svc.version | default $app.targetRevision -}}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ $env }}-{{ $name }}-app
  namespace: argocd
  labels:
    project: {{ $project }}
    env: {{ $env }}
    component: {{ $name }}
    version: {{ $targetRev }}
  annotations:
    argocd.argoproj.io/sync-wave: {{ $app.syncWave | default "0" | quote }}
spec:
  revisionHistoryLimit: 5
  project: {{ $root.Values.project }}
  source:
    repoURL: {{ $root.Values.repoURL }}
    targetRevision: {{ $targetRev }}
    path: {{ $app.path }}
    helm:
      valueFiles:
        - values.yaml
        - values-{{ $env }}.yaml
      {{- if and $svc.version $app.imageRepo }}
      values: |
        workload:
          image: {{ printf "%s:%s" $app.imageRepo $svc.version }}
      {{- end }}
  destination:
    name: {{ $root.Values.cluster }}
    namespace: {{ $app.namespace }}
  syncPolicy:
    {{- if $root.Values.automated }}
    automated:
      prune: true
      selfHeal: true
    {{- end }}
    retry:
      limit: 3
      backoff:
        duration: 30s
        maxDuration: 5m
        factor: 2
    syncOptions:
      - CreateNamespace=true
  ignoreDifferences:
    - group: autoscaling
      kind: HorizontalPodAutoscaler
      jsonPointers:
        - /spec/replicas
{{- end -}}
