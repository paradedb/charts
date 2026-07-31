# CNPGScheduledBackupStalled

## Description

The `CNPGScheduledBackupStalled` alert is triggered when a ScheduledBackup's `nextScheduleTime` is more than an hour in the past.

The operator advances `nextScheduleTime` each time it triggers a backup. A time that has passed and not moved means the schedule is no longer being reconciled — the operator is not creating Backup objects for this cluster.

This is a different failure from a backup that runs and errors. **Backups stop silently rather than failing**, so nothing produces a failed Backup object and `CNPGBackupFailed` never fires. Without this alert, the first signal would be `CNPGBackupStale` 26 hours later.

## Impact

No new backups are being attempted. The recovery window stops advancing from the moment the schedule stalled, and stays frozen until someone notices.

## Diagnosis

Check the ScheduledBackup's recorded times:

```sh
kubectl get scheduledbackups.postgresql.cnpg.io -n <namespace> <name> \
  -o jsonpath='{.status.lastCheckTime}{"\n"}{.status.lastScheduleTime}{"\n"}{.status.nextScheduleTime}{"\n"}'
```

`lastCheckTime` is the useful one: it is when the operator last looked at this object. If it is also stale, the operator is not reconciling — the problem is the operator, not the schedule.

Check the operator is running and look for errors mentioning this cluster:

```sh
kubectl get pods -n cnpg-system
kubectl logs -n cnpg-system deploy/cnpg-controller-manager --since=2h | grep -i <cluster>
```

Also confirm the ScheduledBackup still points at a cluster that exists, and that it is not suspended:

```sh
kubectl get scheduledbackups.postgresql.cnpg.io -n <namespace> <name> -o yaml | grep -E 'suspend|cluster:'
```

## Mitigation

If the operator is unhealthy, that is the incident — a stalled schedule is a symptom, and every cluster it manages is affected, not just this one.

If the ScheduledBackup is suspended and should not be, unsuspend it.

If the schedule itself is malformed, correct the cron expression. The operator will not advance `nextScheduleTime` past an expression it cannot parse.

Once reconciliation resumes, take a backup by hand to close the gap that accumulated while the schedule was stalled:

```sh
kubectl cnpg backup <cluster> -n <namespace>
```
