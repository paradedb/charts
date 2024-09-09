# CNPGBackupFailed

## Description

The `CNPGBackupFailed` alert is triggered when a CloudNativePG cluster's most recent backup attempt failed, meaning its `lastFailedBackup` is more recent than its `lastSuccessfulBackup`, or a failure exists and there has never been a successful backup at all. The alert clears on its own once a backup succeeds.

## Impact

The newest restorable copy is older than it should be, and the recovery window stops advancing for as long as the failures continue.

A single failed nightly run is usually not urgent on its own. It becomes urgent when it repeats, which is why `CNPGBackupStale` exists as the critical backstop at 26 hours.

## Diagnosis

- Find the failed Backup object and read its error, which is usually in `.status.error`:

```bash
kubectl get -n <namespace> backups --sort-by=.status.startedAt -o wide | tail
kubectl describe -n <namespace> backup/<backup-name>
```

- Check the instance logs for the backup window:

```bash
kubectl logs -n <namespace> pod/<instance-pod-name> -c postgres --since=24h | grep -i backup
```

Common causes:

- Object store credentials that expired, were rotated, or lost a permission on the IAM role
- Bucket access, where the bucket was moved or renamed, or its policy changed
- Disk pressure on the instance taking the backup, in which case `CNPGClusterLowDiskSpace` is usually firing too
- The instance being backed up was unavailable when the run started

## Mitigation

Fix the underlying cause, then trigger a backup rather than waiting for the next scheduled run:

```bash
kubectl cnpg backup paradedb -n <namespace>
```

If credentials were the cause, verify the fix end to end rather than assuming. A corrected secret that was never reloaded fails again at the next run, quietly, until this alert fires a second time.

If backups are succeeding but the recovery point is still frozen, WAL archiving rather than the base backup is the problem. See the [`CNPGContinuousArchivingFailed`](./CNPGContinuousArchivingFailed.md) runbook.
