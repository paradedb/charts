# CNPGBackupStale

## Description

The `CNPGBackupStale` alert is triggered when a CloudNativePG cluster's most recent successful backup is older than the configured maximum age.

The default is 26 hours for nightly backups. In Charts, set `cluster.monitoring.prometheusRule.backupStaleAfterHours` to the backup interval plus grace, for example `170` for weekly backups. The alert does not distinguish why the backup is old: it fires whether backups have been failing, whether the ScheduledBackup stopped being reconciled, or whether backups were switched off and nobody noticed.

This is the only backup alert that fires when backups stop happening silently. `CNPGBackupFailed` needs a failure to report, and a backup that is never attempted never fails.

## Impact

The most recent base backup is older than expected, increasing recovery time and dependence on retained WAL. Verify the available backups and WAL before assessing recoverability.

Where continuous WAL archiving is enabled, point-in-time recovery may still reach past the last base backup. Check that archiving is healthy before assuming the full window is lost, since the [`CNPGContinuousArchivingFailed`](./CNPGContinuousArchivingFailed.md) alert covers the case where it is not.

## Diagnosis

- Check the backup timestamps in the monitoring system, scoped to the affected cluster:

```promql
barman_cloud_cloudnative_pg_io_last_available_backup_timestamp{namespace="<namespace>",pod=~"<cluster>-[1-9][0-9]*"}
barman_cloud_cloudnative_pg_io_last_failed_backup_timestamp{namespace="<namespace>",pod=~"<cluster>-[1-9][0-9]*"}
```

For built-in backups, use the equivalent `cnpg_collector_last_available_backup_timestamp` and `cnpg_collector_last_failed_backup_timestamp` metrics. Legacy Cluster-status timestamps do not update for plugin backups.

- List recent Backup objects and their phases:

```bash
kubectl get -n <namespace> backups --sort-by=.status.startedAt -o wide
```

Three cases produce this alert, and they need different responses:

- Backups are failing, so recent Backup objects exist in a failed phase. `CNPGBackupFailed` should also be firing; treat that as the primary alert.
- Backups are not being attempted, so there are no recent Backup objects at all. Check the ScheduledBackup, and see [`CNPGScheduledBackupStalled`](./CNPGScheduledBackupStalled.md) for the case where the operator has stopped advancing the schedule.
- Backups are not configured, so the cluster has no `backup` section or no ScheduledBackup exists. The timestamp is then a leftover from whenever backups were last enabled.

## Mitigation

If backups are failing, fix the underlying failure. See the [`CNPGBackupFailed`](./CNPGBackupFailed.md) runbook.

If nothing is being attempted, confirm a ScheduledBackup exists and is being reconciled:

```bash
kubectl get -n <namespace> scheduledbackups -o wide
```

To close the recovery gap immediately rather than waiting for the next scheduled run, trigger a backup by hand:

```bash
kubectl cnpg backup <cluster> -n <namespace> \
  --method=plugin --plugin-name=barman-cloud.cloudnative-pg.io
```

For built-in Barman backups, omit the plugin flags.

If the cluster is genuinely not meant to be backed up, the alert is reporting the truth about a cluster it should not be watching. Scope the rule rather than silencing it, so the exemption is visible in code instead of living in a silence that outlives whoever created it.
