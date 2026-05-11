{{/*
Suffix cho tên K8s Secret do ESO tạo: -dev, -staging, hoặc rỗng (prod).
Khớp manifest Kubernetes / Argo (meo-stationery-*-secrets-dev|staging| không suffix).
*/}}
{{- define "external-secrets.k8sSecretSuffix" -}}
{{- if eq .Values.env "dev" -}}
-dev
{{- else if eq .Values.env "staging" -}}
-staging
{{- end -}}
{{- end -}}
