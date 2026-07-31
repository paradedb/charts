# CNPGBackupFailed

## Description

The `CNPGBackupFailed` alert is triggered when a CloudNativePG cluster's most recent backup attempt failed. Specifically, when the cluster's `lastFailedBackup` is more recent than its `lastSuccessfulBackup` — or when a failure exists and there has never been a successful backup at all.

The second case matters more than it looks. A cluster whose backups have *never* worked has no successful timestamp to compare against, so a naive "failed more recently than succeeded" test would stay silent on the cluster with no backups whatsoever.

The alert clears on its own once a backup succeeds, because a newer success moves the comparison back the other way. It does not need acknowledging or resolving by hand.

## Impact

The newest restorable copy is older than it should be, and the recovery window stops advancing for as long as the failures continue.

A single failed nightly run is usually not urgent on its own — the previous night's backup is still valid. It becomes urgent when it repeats, which is why `CNPGBackupStale` exists as the critical backstop at 26 hours.

## Diagnosis

Find the failed Backup object and read its error:

```sh
kubectl get backups.postgresql.cnpg.io -n <namespace> \
  --sort-by=.status.startedAt -o wide | tail

kubectl describe backups.postgresql.cnpg.io -n <namespace> <backup>
```

The failure reason is usually in `.status.error`. Common causes, roughly in order of likelihood:

- **Object store credentials** — expired, rotated, or an IAM role that lost a permission.
- **Bucket access** — the bucket was moved, renamed, or its policy changed.
- **Disk pressure on the instance taking the backup** — check whether `CNPGClusterLowDiskSpaceWarning` is also firing.
- **The instance being backed up was unavailable** when the run started.

Check the instance logs for the backup window:

```sh
kubectl logs -n <namespace> <cluster>-N -c postgres --since=24h | grep -i backup
```

## Mitigation

Fix the underlying cause, then trigger a backup rather than waiting for the next scheduled run — that both confirms the fix and clears the alert:

```sh
kubectl cnpg backup <cluster> -n <namespace>
```

If credentials were the cause, verify the fix end to end rather than assuming: a corrected secret that was never reloaded will fail again at the next run, quietly, until this alert fires a second time.
