# CNPGContinuousArchivingFailed

## Description

The `CNPGContinuousArchivingFailed` alert is triggered when a CloudNativePG cluster's most recent WAL archival attempt failed more recently than its last successful one.

This is a separate condition from the backup alerts, which look at base backups. A cluster can report `LastBackupSucceeded=True` and `Ready=True` while every WAL segment written since the last base backup has failed to ship.

The alert compares `cnpg_pg_stat_archiver_last_failed_time` against `cnpg_pg_stat_archiver_last_archived_time`, both exported by CloudNativePG from `pg_stat_archiver`. Only the primary archives WAL; replicas report `-1` for both and cannot trigger the alert.

## Impact

Point-in-time recovery is frozen at the last archived segment. Everything written since then exists only on the instance's own volume and is lost with the cluster, however recent the last base backup is.

The data volume also grows for as long as the condition persists, because PostgreSQL retains unarchived WAL so that the backlog can ship once archiving recovers. At 100% disk usage, the cluster will experience downtime and potential data loss.

## Diagnosis

- Inspect the cluster conditions:

```bash
kubectl get cluster --namespace <namespace> <cluster_name> -o 'jsonpath={range .status.conditions[*]}{.type}={.status} {.message}{"\n"}{end}'
```

`ContinuousArchiving=False` carries the underlying error. `exit status 4` from `barman-cloud-wal-archive` is a generic wrapper, so look for the real cause in the instance logs:

```bash
kubectl logs --namespace <namespace> pod/<instance-pod-name> -c postgres | grep -iE "archive|archiving|denied|credential"
```

- Check free space on the data volume, which is the part of this with a deadline:

```bash
kubectl exec --namespace <namespace> pod/<instance-pod-name> -c postgres -- df -h /var/lib/postgresql/data
```

## Mitigation

The cause is usually object store credentials rather than the object store itself.

### Stale IRSA Role

On EKS with IRSA, a common trigger is the IAM role being recreated or renamed. Pods receive `AWS_ROLE_ARN` at admission and keep it for their lifetime, so an instance that was running before the role changed holds an ARN that no longer resolves. It keeps working on cached credentials until they expire, which is why the failure can appear hours after the change that caused it.

Compare what the pod holds against what the service account now advertises:

```bash
kubectl get pod --namespace <namespace> <instance-pod-name> -o 'jsonpath={.spec.containers[0].env[?(@.name=="AWS_ROLE_ARN")].value}{"\n"}'
kubectl get sa --namespace <namespace> <cluster_name> -o 'jsonpath={.metadata.annotations.eks\.amazonaws\.com/role-arn}{"\n"}'
```

If they differ, the instances need new pods. A container restart is not enough, as the ARN is injected at pod admission and restarting in place preserves the stale value. Trigger a rolling restart:

```bash
kubectl annotate cluster --namespace <namespace> <cluster_name> kubectl.kubernetes.io/restartedAt="$(date -u +%Y-%m-%dT%H:%M:%SZ)" --overwrite
```

> [!IMPORTANT]
> CloudNativePG's default `primaryUpdateMethod` restarts the primary in place rather than recreating it. Verify afterwards that every instance pod is new: an instance whose `AGE` did not reset still holds the old ARN and must be deleted so the operator recreates it.

```bash
kubectl get pods --namespace <namespace> -l "cnpg.io/cluster=<cluster_name>" -L cnpg.io/instanceRole
kubectl delete pod --namespace <namespace> <instance-pod-name>
```

### Object Store Configuration

If credentials are not the cause, verify that the bucket and path in `.spec.backup.barmanObjectStore` still exist and that the bucket policy has not changed.

Once archiving works again, PostgreSQL retries on its own and the backlog drains without intervention. Confirm with `ContinuousArchiving=True` and by watching free space on the data volume recover.
