# CNPGClusterLogicalReplicationDisabled

## Description

The `CNPGClusterLogicalReplicationDisabled` alert indicates that a CloudNativePG cluster acting as a logical replication subscriber has had a logical replication subscription disabled.

## Impact

The cluster remains operational, but queries to the subscriber will return outdated (stale) data.

## Diagnosis

- Check the status of the logical replication subscription:

```bash
kubectl exec services/paradedb-rw --namespace <namespace> -- psql -c 'SELECT * FROM pg_subscription;'
```

- Review the PostgreSQL logs for errors related to logical replication:

```bash
kubectl logs services/paradedb-rw --namespace <namespace> | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")'
kubectl logs services/paradedb-rw --namespace <namespace>
```

## Mitigation

Fix the root cause, if applicable, and re-enable the logical replication subscription by running:

```bash
kubectl exec -it services/paradedb-rw --namespace <namespace> -- psql -c 'ALTER SUBSCRIPTION <your_subscription_name> ENABLE;'
```
