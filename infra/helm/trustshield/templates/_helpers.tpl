{{- define "trustshield.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}-api
{{- end }}

{{- define "trustshield.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: trustshield
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
{{- end }}

{{- define "trustshield.selectorLabels" -}}
app.kubernetes.io/name: trustshield
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
