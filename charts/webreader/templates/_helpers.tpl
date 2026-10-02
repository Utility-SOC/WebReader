{{- define "webreader.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "webreader.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "webreader.labels" -}}
app.kubernetes.io/name: {{ include "webreader.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Name of the Secret holding WEBREADER_LLM_API_KEY ("" when using a local provider) */}}
{{- define "webreader.aiSecretName" -}}
{{- if has .Values.ai.captionProvider (list "local" "none") -}}
{{- else if .Values.ai.existingSecret -}}
{{ .Values.ai.existingSecret }}
{{- else -}}
{{ include "webreader.fullname" . }}-llm
{{- end -}}
{{- end }}
