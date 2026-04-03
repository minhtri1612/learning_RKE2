{{/*
Expand the name of the chart.
*/}}
{{- define "template.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "template.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "template.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "template.labels" -}}
helm.sh/chart: {{ include "template.chart" . }}
{{ include "template.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
Dùng nameOverride (= tên service ngắn như "backend", "database") thay vì Release.Name
để selector label ổn định, không phụ thuộc vào tên ArgoCD App.
*/}}
{{- define "template.selectorLabels" -}}
app.kubernetes.io/name: {{ include "template.name" . }}
app.kubernetes.io/instance: {{ .Values.nameOverride | default .Release.Name }}
{{- end }}

{{/*
Image tag: env/*.yaml đặt backend.image.tag / database.image.tag; fallback image.tag rồi appVersion.
*/}}
{{- define "template.imageTagBackend" -}}
{{- $svcName := .Values.currentService | default "backend" -}}
{{- $svc := (index .Values $svcName) | default dict -}}
{{- $i := $svc.image | default dict -}}
{{- $i.tag | default .Values.image.tag | default .Chart.AppVersion -}}
{{- end }}

{{- define "template.imageTagDatabase" -}}
{{- $svcName := .Values.currentService | default "database" -}}
{{- $svc := (index .Values $svcName) | default dict -}}
{{- $i := $svc.image | default dict -}}
{{- $i.tag | default .Values.image.tag | default .Chart.AppVersion -}}
{{- end }}

{{- define "template.imageRepositoryCurrent" -}}
{{- $svcName := .Values.currentService | default "backend" -}}
{{- $svc := (index .Values $svcName) | default dict -}}
{{- $i := $svc.image | default dict -}}
{{- $i.repository | default .Values.image.repository -}}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "template.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "template.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Suffix cho tên K8s Secret: -dev, -staging, hoặc rỗng (prod).
*/}}
{{- define "template.secretSuffix" -}}
{{- if eq .Values.env "dev" -}}
-dev
{{- else if eq .Values.env "staging" -}}
-staging
{{- end -}}
{{- end -}}

{{/*
Tên K8s Secret được ghép động theo quy ước: meo-stationery-<component>-secrets<suffix>
*/}}
{{- define "template.secretName" -}}
{{- $svcName := .Values.currentService | default "backend" -}}
{{- printf "meo-stationery-%s-secrets%s" $svcName (include "template.secretSuffix" .) -}}
{{- end -}}
