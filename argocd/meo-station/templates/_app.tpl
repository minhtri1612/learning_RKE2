{{/*
Một Argo CD Application = một Helm release (chart template/ + app overlay + env tag overlay).

Merge values (Helm -f theo thứ tự):
  1. template/values.yaml        (gốc trong chart)
  2. app/be.yaml | app/db.yaml   (literal theo service)
  3. env/<env>.yaml              (backend.image.tag, database.image.tag — dev team)
*/}}
{{- define "meo-station.app" -}}
{{- $name := .name -}}
{{- $root := .root -}}
{{- $app := index $root.Values.apps $name -}}
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
    path: template
    helm:
      releaseName: {{ $app.releaseName | default (printf "%s-%s" $root.Values.env $name) }}
      valueFiles:
        - {{ $app.valueFile | quote }}
        - {{ printf "../env/%s.yaml" $root.Values.env | quote }}
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
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
{{- end -}}
