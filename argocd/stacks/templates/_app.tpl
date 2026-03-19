{{/*
Sinh 1 ArgoCD Application cho 1 service cụ thể.

Usage:
  {{- include "stacks.app" (dict "name" "backend" "root" $) }}
  {{- include "stacks.app" (dict "name" "database" "root" $) }}

Value hierarchy (last wins):
  1. Chart values.yaml          ← chart defaults
  2. common-values.yaml         ← shared overrides
  3. env-type/<type>-values.yaml ← non-prod hoặc prod
  4. app-version/<env>-values.yaml ← image tag theo môi trường
*/}}
{{- define "stacks.app" -}}
{{- $name    := .name -}}
{{- $root    := .root -}}
{{- $app     := index $root.Values.apps $name -}}
{{- $envType := index ($app.envType | default dict) $root.Values.env | default "non-prod" -}}
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
  sources:
    - repoURL: {{ $root.Values.repoURL }}
      targetRevision: {{ $app.targetRevision | default "main" }}
      path: {{ $app.chartPath }}
      helm:
        values: |
          app:
            name: {{ $name }}
            namespace: {{ $app.namespace }}
        valueFiles:
          - $values/values/{{ $name }}/common-values.yaml
          - $values/values/{{ $name }}/env-type/{{ $envType }}-values.yaml
          - $values/values/{{ $name }}/app-version/{{ $root.Values.env }}-values.yaml
    - repoURL: {{ $root.Values.repoURL }}
      targetRevision: {{ $app.targetRevision | default "main" }}
      ref: values
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
