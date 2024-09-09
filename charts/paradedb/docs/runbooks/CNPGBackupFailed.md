# CNPGBackupFailed

## Description

The `CNPGBackupFailed` alert is triggered when a CloudNativePG cluster's most recent backup attempt failed, meaning the last failed backup timestamp is newer than the last successful backup timestamp, or a failure exists with no prior success. Plugin timestamps come from the `barman_cloud_cloudnative_pg_io_*` metrics; built-in backups use legacy sources. The alert clears on its own once a backup succeeds.

## Impact

The newest restorable copy is older than it should be, and the recovery window stops advancing for as long as the failures continue.

A single failed nightly run is usually not urgent on its own. It becomes urgent when it repeats, which is why `CNPGBackupStale` provides a critical backstop at the configured backup interval plus grace.

## Diagnosis

- Find the failed Backup object and read its error, which is usually in `.status.error`:

```bash
kubectl get -n <namespace> backups --sort-by=.status.startedAt -o wide | tail
kubectl describe -n <namespace> backup/<backup-name>
```

- Check the instance logs for the backup window:

```bash
kubectl logs -n <namespace> pod/<instance-pod-name> -c plugin-barman-cloud --since=24h
```

For built-in backups, check the `postgres` container instead.

Common causes:

- Object store credentials that expired, were rotated, or lost a permission on the IAM role
- Bucket access, where the bucket was moved or renamed, or its policy changed
- Disk pressure on the instance taking the backup, in which case `CNPGClusterLowDiskSpace` is usually firing too
- The instance being backed up was unavailable when the run started

## Mitigation

Fix the underlying cause, then trigger a backup rather than waiting for the next scheduled run:

```bash
kubectl cnpg backup <cluster> -n <namespace> \
  --method=plugin --plugin-name=barman-cloud.cloudnative-pg.io
```

For built-in Barman backups, omit the plugin flags.

If credentials were the cause, verify the fix end to end rather than assuming. A corrected secret that was never reloaded fails again at the next run, quietly, until this alert fires a second time.

If backups are succeeding but the recovery point is still frozen, WAL archiving rather than the base backup is the problem. See the [`CNPGContinuousArchivingFailed`](./CNPGContinuousArchivingFailed.md) runbook.
