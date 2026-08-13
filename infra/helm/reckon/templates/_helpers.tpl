{{- define "reckon.fullname" -}}
{{ .Release.Name }}-{{ .Chart.Name }}
{{- end }}

{{- define "reckon.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "reckon.warehouseSecretName" -}}
{{- default (printf "%s-warehouse" (include "reckon.fullname" .)) .Values.warehouse.existingSecret -}}
{{- end }}

{{- define "reckon.pipelineContainer" -}}
- name: pipeline
  image: {{ .Values.images.pipeline }}
  imagePullPolicy: {{ .Values.images.pullPolicy }}
  envFrom:
    - secretRef:
        name: {{ include "reckon.warehouseSecretName" . }}
  env:
    - name: DBT_TARGET
      value: {{ .Values.pipeline.dbtTarget | quote }}
    {{- if .Values.mongo.enabled }}
    - name: MONGO_URI
      value: "mongodb://{{ include "reckon.fullname" . }}-mongo:{{ .Values.mongo.port }}"
    - name: MONGO_DB
      value: {{ .Values.mongo.db | quote }}
    {{- end }}
    {{- if .Values.monitoring.enabled }}
    - name: OTEL_ENABLED
      value: "true"
    - name: PUSHGATEWAY_URL
      value: "http://{{ include "reckon.fullname" . }}-pushgateway:{{ .Values.monitoring.pushgateway.port }}"
    {{- end }}
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: "1"
      memory: 1Gi
{{- end }}
