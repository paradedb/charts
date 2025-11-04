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

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Receipt Lag (Critical)** | `NOW() - last_msg_receipt_time` (Network connectivity) | Time since last data **received** (300s+) | Network connectivity, publisher health |
| **Apply Lag (Critical)** | `NOW() - latest_end_time` (Subscriber performance) | Time since data was last **applied** (300s+) | Subscriber resources, I/O performance, blocking queries |
| **Distance Lag (Critical)** | `received_lsn - latest_end_lsn` (System backlog) | Amount of WAL data pending (10GB+) | Overall system capacity, storage, subscriber processing |
| **Receipt Lag (Warning)** | `NOW() - last_msg_receipt_time` (Network connectivity) | Time since last data **received** (60s+) | Network performance, publisher load |

**Key Difference**: Receipt lag specifically measures **network connectivity and publisher health** - it tells you whether the subscriber is receiving data at all. Apply lag measures subscriber processing performance, while distance lag measures the overall system backlog.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/
