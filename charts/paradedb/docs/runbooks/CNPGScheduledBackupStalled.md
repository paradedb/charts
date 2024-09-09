# CNPGScheduledBackupStalled

## Description

The `CNPGScheduledBackupStalled` alert is triggered when a ScheduledBackup's `nextScheduleTime` is more than an hour in the past.

The operator advances `nextScheduleTime` each time it triggers a backup. A time that has passed without moving means the schedule is no longer being reconciled, so the operator is not creating Backup objects for this cluster.

This is a different failure from a backup that runs and errors. Backups stop silently rather than failing, so nothing produces a failed Backup object and `CNPGBackupFailed` never fires. Without this alert, the first signal would be `CNPGBackupStale` 26 hours later.

## Impact

No new backups are being attempted. The recovery window stops advancing from the moment the schedule stalled, and stays frozen until someone notices.

## Diagnosis

- Check the ScheduledBackup's recorded times:

```bash
kubectl get -n <namespace> scheduledbackup/<scheduledbackup-name> -o 'jsonpath={.status.lastCheckTime}{"\n"}{.status.lastScheduleTime}{"\n"}{.status.nextScheduleTime}{"\n"}'
```

`lastCheckTime` is the useful one, since it is when the operator last looked at this object. If it is also stale, the operator is not reconciling and the problem is the operator rather than the schedule.

- Check the operator is running, and look for errors mentioning this cluster:

```bash
kubectl get -n cnpg-system pods -l "app.kubernetes.io/name=cloudnative-pg"
kubectl logs -n cnpg-system -l "app.kubernetes.io/name=cloudnative-pg" --since=2h | grep -i paradedb
```

- Confirm the ScheduledBackup still points at a cluster that exists, and that it is not suspended:

```bash
kubectl get -n <namespace> scheduledbackup/<scheduledbackup-name> -o yaml | grep -E 'suspend|cluster:'
```

## Mitigation

If the operator is unhealthy, that is the incident. A stalled schedule is a symptom, and every cluster the operator manages is affected, not just this one.

If the ScheduledBackup is suspended and should not be, unsuspend it.

If the schedule itself is malformed, correct the cron expression. The operator will not advance `nextScheduleTime` past an expression it cannot parse.

Once reconciliation resumes, take a backup by hand to close the gap that accumulated while the schedule was stalled:

```bash
kubectl cnpg backup paradedb -n <namespace>
```
