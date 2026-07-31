# CNPGContinuousArchivingFailed

## Description

The `CNPGContinuousArchivingFailed` alert is triggered when a CloudNativePG cluster's most recent WAL archival attempt failed more recently than its last successful one.

This is a distinct condition from the backup alerts, and it is the one that hides. `CNPGBackupFailed` and `CNPGBackupStale` both look at *base backups*. A cluster whose last nightly backup succeeded reports `LastBackupSucceeded=True` and `Ready=True` while every WAL segment since has failed to ship. Nothing in the cluster's headline status says otherwise.

The alert compares `cnpg_pg_stat_archiver_last_failed_time` against `cnpg_pg_stat_archiver_last_archived_time`, both exported by CloudNativePG's default metrics from `pg_stat_archiver`. Only the primary archives; replicas report `-1` for both and cannot trigger it.

## Impact

**Point-in-time recovery is frozen at the last archived segment.** Everything written since exists only on the instance's own volume. If the cluster is lost while this is firing, recovery goes back to that point regardless of how recent the last base backup was — the base backup alone cannot replay past its own timestamp.

**The data volume grows.** PostgreSQL retains unarchived WAL rather than discarding it, precisely so the backlog can ship once archiving recovers. That is the desired behaviour, but it means the volume fills for as long as the condition persists, and a full PGDATA volume takes the database down hard.

The retention is also why recovery is usually clean: once archiving works again the backlog drains to the object store and the recovery chain heals with no gap, provided the volume never filled.

## Diagnosis

Confirm the cluster's own view:

```sh
kubectl get cluster -n <namespace> <cluster> \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status} {.message}{"\n"}{end}'
```

`ContinuousArchiving=False` carries the underlying error. `exit status 4` from `barman-cloud-wal-archive` is the generic wrapper — the real cause is in the instance logs:

```sh
kubectl logs -n <namespace> <cluster>-<n> -c postgres | grep -iE "archiv|denied|credential"
```

Check headroom on the data volume, since this is the part with a deadline:

```sh
kubectl exec -n <namespace> <cluster>-<n> -c postgres -- df -h /var/lib/postgresql/data
```

## Mitigation

The cause is most often object store credentials rather than the object store itself.

On EKS with IRSA, a common trigger is the IAM role being recreated or renamed. Pods receive `AWS_ROLE_ARN` at admission and keep it for their lifetime, so an instance that was running before the role changed holds an ARN that no longer resolves. It continues working on cached credentials until they expire, then fails to refresh — which is why the failure can appear hours after the change that caused it.

Compare what the pod holds against what the service account now advertises:

```sh
kubectl get pod -n <namespace> <cluster>-<n> \
  -o jsonpath='{.spec.containers[0].env[?(@.name=="AWS_ROLE_ARN")].value}{"\n"}'
kubectl get sa -n <namespace> <cluster> \
  -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}{"\n"}'
```

If they differ, the instances need genuinely new pods. A container restart is not enough — the ARN is injected at pod admission, so restarting in place preserves the stale value. Trigger a rolling restart:

```sh
kubectl annotate cluster -n <namespace> <cluster> \
  kubectl.kubernetes.io/restartedAt="$(date -u +%Y-%m-%dT%H:%M:%SZ)" --overwrite
```

Note that CloudNativePG's default `primaryUpdateMethod` restarts the primary in place rather than recreating it. Check afterwards that every instance pod is genuinely new — an instance whose `AGE` did not reset still holds the old ARN and must be deleted so it is recreated:

```sh
kubectl get pods -n <namespace> -l cnpg.io/cluster=<cluster> -L cnpg.io/instanceRole
kubectl delete pod -n <namespace> <cluster>-<n>
```

Once credentials work, archiving resumes on PostgreSQL's own retry and the backlog drains without intervention. Confirm with `ContinuousArchiving=True` and by watching the data volume free space recover.

If credentials are not the cause, check that the object store bucket and path in `.spec.backup.barmanObjectStore` still exist and that the bucket policy has not changed.
