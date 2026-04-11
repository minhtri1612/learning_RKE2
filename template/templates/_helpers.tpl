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

{{/*
Tên Secret pod mount: ưu tiên <service>.secrets.target.name (config/env), fallback template.secretName.
*/}}
{{- define "template.serviceSecretName" -}}
{{- $svcName := .Values.currentService | default "backend" -}}
{{- $svc := index .Values $svcName | default dict -}}
{{- if and $svc.secrets $svc.secrets.target $svc.secrets.target.name -}}
{{- $svc.secrets.target.name -}}
{{- else -}}
{{- include "template.secretName" . -}}
{{- end -}}
{{- end -}}

{{/*
Pod template (metadata + spec) shared by Rollout and Deployment for stateless workloads.
*/}}
{{- define "template.workloadPodSpec" -}}
{{- $svcName := .Values.currentService | default "backend" }}
{{- $svc := (index .Values $svcName) | default dict }}
{{- $cfg := $svc.configs | default dict }}
{{- $cfgEnv := $cfg.env | default list }}
{{- $files := $cfg.files | default list }}
{{- $hasFiles := gt (len $files) 0 }}
{{- $filesMount := $cfg.filesMountPath | default "/config/files" }}
{{- $useES := .Values.useExternalSecrets }}
{{- if and $svc.secrets (hasKey $svc.secrets "useExternalSecrets") }}
{{- $useES = $svc.secrets.useExternalSecrets }}
{{- end }}
metadata:
  {{- with .Values.podAnnotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  labels:
    {{- include "template.labels" . | nindent 4 }}
    {{- with .Values.podLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  {{- with .Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  serviceAccountName: {{ include "template.serviceAccountName" . }}
  {{- with .Values.podSecurityContext }}
  securityContext:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  containers:
    - name: {{ .Chart.Name }}
      {{- with .Values.securityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      image: "{{ include "template.imageRepositoryCurrent" . }}:{{ include "template.imageTagBackend" . }}"
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      ports:
        - name: {{ .Values.service.portName | default "http" }}
          containerPort: {{ .Values.service.containerPort | default .Values.service.port }}
          protocol: TCP
      {{- with .Values.livenessProbe }}
      livenessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.readinessProbe }}
      readinessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.resources }}
      resources:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- if $useES }}
      envFrom:
        - secretRef:
            name: {{ include "template.serviceSecretName" . }}
      {{- end }}
      {{- if or .Values.extraEnv (gt (len $cfgEnv) 0) }}
      env:
        {{- with .Values.extraEnv }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
        {{- if gt (len $cfgEnv) 0 }}
        {{- toYaml $cfgEnv | nindent 8 }}
        {{- end }}
      {{- end }}
      {{- $vm := .Values.volumeMounts }}
      {{- if or $vm (and .Values.runtimeConfig.enabled .Values.runtimeConfig.data) $hasFiles }}
      volumeMounts:
        {{- with $vm }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
        {{- if and .Values.runtimeConfig.enabled .Values.runtimeConfig.data }}
        - name: app-config
          mountPath: {{ .Values.runtimeConfig.mountPath | default "/app/config" }}
          readOnly: true
        {{- end }}
        {{- if $hasFiles }}
        - name: svc-config-files
          mountPath: {{ $filesMount }}
          readOnly: true
        {{- end }}
      {{- end }}
  {{- if or .Values.volumes (and .Values.runtimeConfig.enabled .Values.runtimeConfig.data) $hasFiles }}
  volumes:
    {{- with .Values.volumes }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
    {{- if and .Values.runtimeConfig.enabled .Values.runtimeConfig.data }}
    - name: app-config
      configMap:
        name: {{ include "template.fullname" . }}-config
    {{- end }}
    {{- if $hasFiles }}
    - name: svc-config-files
      configMap:
        name: {{ include "template.fullname" . }}-files
    {{- end }}
  {{- end }}
  {{- with .Values.nodeSelector }}
  nodeSelector:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.affinity }}
  affinity:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.tolerations }}
  tolerations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
