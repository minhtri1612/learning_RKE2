{{- define "generic-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "generic-app.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "generic-app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "generic-app.labels" -}}
helm.sh/chart: {{ include "generic-app.chart" . }}
{{ include "generic-app.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "generic-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "generic-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "generic-app.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "generic-app.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Map Resource Tier for Deployments / StatefulSets
*/}}
{{- define "generic-app.resources" -}}
{{- if eq (.Values.app_type | default "api") "database" -}}
{{- $tier := .Values.db_tier | default "dev-basic" -}}
{{- $config := index .Values.db_tiers.profiles $tier -}}
resources:
  limits:
    memory: {{ $config.ram_limit | quote }}
  requests:
    memory: {{ $config.ram_limit | quote }}
{{- else -}}
{{- $tier := .Values.tier | default "micro" -}}
{{- $config := index .Values.app_tiers.profiles $tier -}}
resources:
  limits:
    cpu: {{ $config.cpu_limit | quote }}
    memory: {{ $config.ram_limit | quote }}
  requests:
    cpu: {{ $config.cpu_limit | quote }}
    memory: {{ $config.ram_limit | quote }}
{{- end -}}
{{- end -}}
