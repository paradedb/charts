{{- define "cluster.backup" -}}
{{- if .Values.backups.enabled }}
backup:
  target: "prefer-standby"
  retentionPolicy: {{ .Values.backups.retentionPolicy }}
  barmanObjectStore:
    wal:
      compression: {{ .Values.backups.wal.compression }}
      {{- if .Values.backups.wal.encryption }}
      encryption: {{ .Values.backups.wal.encryption }}
      {{- end }}
      maxParallel: {{ .Values.backups.wal.maxParallel }}
    data:
      compression: {{ .Values.backups.data.compression }}
      {{- if .Values.backups.data.encryption }}
      encryption: {{ .Values.backups.data.encryption }}
      {{- end }}
      jobs: {{ .Values.backups.data.jobs }}

    {{- $d := dict "chartFullname" (include "cluster.fullname" .) "scope" .Values.backups "secretPrefix" "backup" }}
    {{- include "cluster.barmanObjectStoreConfig" $d | nindent 2 }}
{{- end }}
{{- end }}
