{{/*
Sinh 1 ArgoCD Application cho 1 service cụ thể.

Usage:
  {{- include "meo-station.app" (dict "name" "backend" "root" $) }}
  {{- include "meo-station.app" (dict "name" "database" "root" $) }}

Value hierarchy (last wins) - IDP Pattern:
  1. 1-platform-engine/generic-app      ← Engine
  2. 2-platform-guardrails/<env>.yaml   ← DevOps Env rules
  3. 3-developer-workspace/<env>/<app>  ← Dev Spec
*/}}
{{- define "meo-station.app" -}}
{{- $name    := .name -}}
{{- $root    := .root -}}
{{- $app     := index $root.Values.apps $name -}}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ $root.Values.env }}-{{ $root.Values.name }}-{{ $name }}-app
  namespace: argocd
  labels:
    project: {{ $root.Values.name }}
    env: {{ $root.Values.env }}
    component: {{ $name }}
  annotations:
    argocd.argoproj.io/sync-wave: {{ $app.syncWave | default "0" | quote }}
spec:
  revisionHistoryLimit: 5
  project: {{ $root.Values.project }}
  source:
    repoURL: {{ $root.Values.repoURL }}
    targetRevision: {{ $app.targetRevision | default "main" }}
    path: .manifest/{{ $root.Values.env }}/{{ $name }}
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
  # HPA owns Deployment.spec.replicas. Without this, Argo selfHeal fights HPA → pods flap (scale up/down loop).
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
{{- end -}}
