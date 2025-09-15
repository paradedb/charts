# CNPGClusterLogicalReplicationStuck

## Description

The `CNPGClusterLogicalReplicationStuck` alert indicates that a CloudNativePG cluster acting as a logical replication subscriber has not made any progress in applying WAL data from its publication for more than 600 seconds. This is determined by the presence of "finished at" messages in the PostgreSQL logs without any corresponding progress in the `pg_stat_subscription` view.

## Impact

The cluster is still operational, but queries to the subscriber will return stale data.

## Diagnosis

- Check the status of the logical replication subscription:

```bash
kubectl exec services/paradedb-rw --namespace <namespace> -- psql -c 'SELECT * FROM pg_subscription;'
```

- Check the PostgreSQL logs for errors related to the logical replication subscription:

```bash
kubectl logs services/paradedb-rw --namespace <namespace> | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")
kubectl logs services/paradedb-rw --namespace <namespace> | jq 'select(.record.message | contains("finished at"))'
```

## Mitigation

The most common reason for a stuck logical replication subscription is the presence of conflicts. Please refer to the [PostgreSQL Documentation](https://www.postgresql.org/docs/current/logical-replication-conflicts.html) on how to handle logical replication conflicts. Once the conflicts are resolved, the subscription will restart applying changes automatically.
