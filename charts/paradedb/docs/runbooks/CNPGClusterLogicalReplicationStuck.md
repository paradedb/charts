# CNPGClusterLogicalReplicationStuck

## Meaning

The `CNPGClusterLogicalReplicationStuck` alert indicates that a CloudNativePG cluster with a Logical Replication Subscription has not made any progress in applying WAL data from its publication for more than 600 seconds. This is determined by the presence of "finished at" messages in the PostgreSQL logs without any corresponding progress in the `pg_stat_subscription` view.

## Impact

The cluster is still operational, but queries to the subscriber will return stale data.

## Diagnosis

* Check the status of the logical replication subscription:

  ```bash
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SELECT * FROM pg_subscription;'
  ```

* Check the PostgreSQL logs for errors related to the logical replication subscription:

  ```bash
  kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")
  kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.message | contains("finished at"))'
  ```

## Mitigation

If the subscription is stuck and not making progress, you can skip to the latest LSN by running:

  ```bash
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'ALTER SUBSCRIPTION subscription_name SKIP ( lsn = 'FINISH_LSN' );'
  ```

If the subscription is disabled, re-enable it by running:


  ```bash
  kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql -c 'ALTER SUBSCRIPTION your_subscription_name ENABLE;'
  ```
