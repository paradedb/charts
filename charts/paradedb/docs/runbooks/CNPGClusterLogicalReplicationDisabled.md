# CNPGClusterLogicalReplicationDisabled

## Meaning

The `CNPGClusterLogicalReplicationDisabled` alert indicates that a CloudNativePG cluster with a Logical Replication Subscription has had a logical replication disabled.

## Impact

The cluster remains operational, but queries to the subscriber will return outdated (stale) data.

## Diagnosis

* Check the status of the logical replication subscription:

  ```bash
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SELECT * FROM pg_subscription;'
  ```

* Review the PostgreSQL logs for errors related to logical replication:

  ```bash
  kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")'
  kubectl logs services/paradedb-rw --namespace NAMESPACE
  ```

## Mitigation

Re-enable the logical replication subscription by running:

```bash
kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql -c 'ALTER SUBSCRIPTION your_subscription_name ENABLE;'
```
