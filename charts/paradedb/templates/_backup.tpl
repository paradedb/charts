{{- define "cluster.backup" -}}
{{- if and .Values.backups.enabled ((eq .Values.backups.method "barmanObjectStore")) }}
backup:
  target: "prefer-standby"
  retentionPolicy: {{ .Values.backups.barmanObjectStore.retentionPolicy }}
  barmanObjectStore:
    wal:
      compression: {{ .Values.backups.barmanObjectStore.wal.compression }}
      {{- if .Values.backups.barmanObjectStore.wal.encryption }}
      encryption: {{ .Values.backups.barmanObjectStore.wal.encryption }}
      {{- end }}
      maxParallel: {{ .Values.backups.barmanObjectStore.wal.maxParallel }}
    data:
      compression: {{ .Values.backups.barmanObjectStore.data.compression }}
      {{- if .Values.backups.barmanObjectStore.data.encryption }}
      encryption: {{ .Values.backups.barmanObjectStore.data.encryption }}
      {{- end }}
      jobs: {{ .Values.backups.barmanObjectStore.data.jobs }}

    {{- $d := dict "chartFullname" (include "cluster.fullname" .) "scope" .Values.backups.barmanObjectStore "secretPrefix" "backup" }}
    {{- include "cluster.barmanObjectStoreConfig" $d | nindent 2 }}
{{- end }}
{{- end }}
