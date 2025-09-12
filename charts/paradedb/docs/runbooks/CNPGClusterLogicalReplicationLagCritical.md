# CNPGClusterLogicalReplicationLagCritical

## Meaning

The `CNPGClusterLogicalReplicationLagCritical` alert indicates that a CloudNativePG cluster with a logical replication subscription has not received any WAL data from its publication for more than 300 seconds. This is determined by the `now() - last_msg_receipt_time` value from `pg_stat_subscription`.

## Impact

The cluster remains operational, but queries to the subscriber will return stale data.

## Diagnosis

* Check the PostgreSQL logs for errors related to the logical replication subscription:

  ```bash
  kubectl logs services/paradedb-rw --namespace NAMESPACE
  ```

* Suboptimal PostgreSQL configuration, particularly an insufficient value for `max_logical_replication_workers` or `max_worker_processes`, can lead to replication lag.

  Review the _CloudNativePG Parameters_ in the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard] or by running:

  ```bash
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SHOW max_worker_processes'
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SHOW max_logical_replication_workers'
  ```

  * Ensure `max_worker_processes` is set according to the formula: `max_worker_processes >= max_parallel_workers + max_parallel_maintenance_workers + max_logical_replication_workers`.

* Check for network issues or congestion on the node's network interface using the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard].

## Mitigation

* Adjust the PostgreSQL parameters as follows:
* Helm: `cluster.postgresql.parameters.max_logical_replication_workers`
* ParadeDB BYOC Terraform: `paradedb.postgresql.parameters.max_logical_replication_workers`

* Ensure your instance types provide sufficient network performance for your workload.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/
