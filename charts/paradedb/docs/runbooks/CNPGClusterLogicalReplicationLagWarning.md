# CNPGClusterLogicalReplicationLagWarning

## Meaning

The `CNPGClusterLogicalReplicationLagWarning` alert indicates that a CloudNativePG cluster with a Logical Replication Subscription has not received any WAL data from its publication for more than 60 seconds. This is determined by the `now() - last_msg_receipt_time` value from `pg_stat_subscription`.

## Impact

The cluster is still operational, but queries to the subscriber will return stale data.

## Diagnosis

* Check the PostgreSQL logs for errors related to the logical replication subscription:

  ```bash
  kubectl logs services/paradedb-rw --namespace NAMESPACE
  ```

* Suboptimal PostgreSQL configuration, in particular an insufficiently small setting of `max_logical_replication_workers` or `max_worker_processes` can lead to replication lag.

  Navigate to the _CloudNativePG Parameters_ from the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard] or by running:

  ```bash
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SHOW max_worker_processes'
  kubectl exec services/paradedb-rw --namespace NAMESPACE -- psql -c 'SHOW max_logical_replication_workers'
  ```

  * Ensure `max_worker_processes` is correctly sized according to the formula: `max_worker_processes >= max_parallel_workers + max_parallel_maintenance_workers + max_logical_replication_workers`.

* Check for network issues and network congestion of the node network interface from the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard].

## Mitigation

* Correct the PostgreSQL parameters by setting:
  * Helm: `cluster.postgresql.parameters.max_logical_replication_workers`
  * ParadeDB BYOC Terraform: `paradedb.postgresql.parameters.max_logical_replication_workers`

* Make sure your instance types have sufficient network performance for your workload.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/
