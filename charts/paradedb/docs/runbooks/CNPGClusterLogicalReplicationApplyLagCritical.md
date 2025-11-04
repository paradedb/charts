# CNPGClusterLogicalReplicationApplyLagCritical

## Meaning

The `CNPGClusterLogicalReplicationApplyLagCritical` alert indicates that a CloudNativePG cluster with a logical replication subscription has a time delay of more than 300 seconds (5 minutes) between receiving data from the publisher and actually applying it. This is calculated as `NOW() - latest_end_time` from `pg_stat_subscription`.

This alert specifically measures **subscriber processing performance** - it indicates that while data is being received from the publisher, the subscriber is struggling to process and apply those changes fast enough. Common reasons include:

* The subscriber is under heavy CPU/memory load and cannot process transactions quickly enough.
* Disk I/O bottlenecks on the subscriber, especially slow storage or high write latency.
* Resource contention with other workloads on the subscriber instance.
* Complex transactions on the publisher that require significant processing time on the subscriber.
* Locks or blocking queries on subscriber tables preventing apply operations.
* Insufficient `max_logical_replication_workers` or `max_parallel_workers` configured on the subscriber.
* Outdated statistics leading to suboptimal query plans on the subscriber.

## Impact

The cluster remains operational, but queries to the subscriber will return significantly stale data. The data gap between publisher and subscriber will continue to grow until the apply performance issue is resolved.

## Diagnosis

1. From the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard]:

   * In the _Logical Replication_ section, examine the _Apply Lag_ graph. Look at both the absolute lag time and its trend. An increasing trend indicates the problem is worsening.
   * Check the _Workload_ section for high CPU, memory, or disk I/O utilization on the subscriber.
   * In the _Connections_ section, look for high connection counts or long-running queries that might be blocking apply operations.

2. Connect via psql to check the logical replication subscription status:

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   Check the apply worker activity and performance:

   ```sql
   SELECT s.subname,
          s.worker_type,
          s.pid,
          s.received_lsn,
          s.latest_end_lsn,
          s.last_msg_send_time,
          s.last_msg_receipt_time,
          s.latest_end_time,
          NOW() - s.latest_end_time AS apply_lag_seconds,
          a.state, a.wait_event_type, a.wait_event,
          a.query,
          pg_blocking_pids(a.pid) AS blocked_by
   FROM pg_stat_subscription AS s
   LEFT JOIN pg_stat_activity   AS a ON a.pid = s.pid
   WHERE s.worker_type = 'apply'
   ORDER BY s.subname;
   ```

   * If `apply_lag_seconds` is consistently high and increasing, the subscriber is struggling to keep up.
   * If `wait_event_type = 'Lock'`, the apply worker is blocked by another transaction. Use `pg_blocking_pids(pid)` to identify the blocking session.
   * If `wait_event_type = 'LWLock'` and `wait_event IN ('wal_write', 'wal_flush')`, the worker is waiting on WAL operations, indicating I/O bottlenecks.
   * If `wait_event_type = 'Activity'` and `wait_event = 'LogicalApplyMain'`, the worker is actively applying but may be overwhelmed by transaction volume.

   To identify blocking sessions:

   ```sql
   WITH apply AS (
     SELECT s.pid
     FROM pg_stat_subscription s
     WHERE s.worker_type = 'apply'
   ),
   blk AS (
     SELECT unnest(pg_blocking_pids(a.pid)) AS blocker
     FROM apply ap
     JOIN pg_stat_activity a ON a.pid = ap.pid
   )
   SELECT b.blocker AS blocker_pid,
          sa.usename, sa.state, sa.wait_event_type, sa.wait_event, sa.query,
          sa.backend_start, sa.query_start
   FROM blk b
   JOIN pg_stat_activity sa ON sa.pid = b.blocker;
   ```

3. Check for resource-intensive queries on the subscriber:

   ```sql
   SELECT pid, now() - query_start AS duration, query, state, wait_event_type, wait_event
   FROM pg_stat_activity
   WHERE state != 'idle'
     AND pid NOT IN (SELECT pid FROM pg_stat_subscription WHERE pid IS NOT NULL)
   ORDER BY duration DESC
   LIMIT 10;
   ```

4. Check subscription statistics for error patterns:

   ```sql
   SELECT subname, apply_error_count, sync_error_count, stats_reset
   FROM pg_stat_subscription_stats;
   ```

   * Increasing error counts indicate recurring issues that need to be addressed.

5. Check table-specific replication progress:

   ```sql
   SELECT sub.subname,
          sr.srrelid::regclass AS table_name,
          sr.srsubstate,
          sr.srsublsn
   FROM pg_subscription_rel AS sr
   JOIN pg_subscription     AS sub ON sub.oid = sr.srsubid
   WHERE sr.srsubstate != 'r'  -- 'r' = ready, others indicate sync in progress
   ORDER BY sub.subname, table_name;
   ```

## Mitigation

Depending on the cause, try the following:

* If the subscriber is under heavy load, consider scaling up its resources (CPU, memory) or offloading read queries to other replicas.
* If there are disk I/O bottlenecks, consider using a storage class with higher IOPS and throughput. Update the `paradedb.storage.storageClass` and `paradedb.walStorage.storageClass` parameters in the configuration.
* If the apply worker is blocked by long-running queries, identify and terminate the blocking sessions:

   ```sql
   SELECT pg_terminate_backend(blocker_pid)
   FROM (
     SELECT unnest(pg_blocking_pids(a.pid)) AS blocker_pid
     FROM pg_stat_subscription s
     JOIN pg_stat_activity a ON a.pid = s.pid
     WHERE s.worker_type = 'apply'
   ) blocking_sessions;
   ```

* Adjust the `max_logical_replication_workers` and `max_parallel_workers` parameters on the subscriber to allow more parallel processing:

   ```bash
   # Helm: cluster.postgresql.parameters.max_logical_replication_workers
   # Terraform: paradedb.postgresql.parameters.max_logical_replication_workers
   ```

* Optimize the subscriber workload:
   * Run `ANALYZE` on large tables to ensure accurate statistics for query planning.
   * Consider reducing the number of indexes on the subscriber if write performance is critical.
   * Review and optimize long-running queries that might be blocking apply operations.

* If the issue persists due to high transaction volume from the publisher, consider:
   * Implementing publication filters to replicate only necessary tables/columns.
   * Breaking large transactions into smaller ones on the publisher.
   * Adding more subscriber instances to distribute the load.

* Check for and resolve any data conflicts or constraint violations that might be causing apply failures:

   ```bash
   kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")'
   ```

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Apply Lag (Critical)** | `NOW() - latest_end_time` (Subscriber performance) | Time since data was last **applied** to subscriber | Subscriber resources, I/O performance, blocking queries |
| **Receipt Lag (Critical)** | `NOW() - last_msg_receipt_time` (Network connectivity) | Time since last data **received** from publisher | Network connectivity, publisher health |
| **Distance Lag (Critical)** | `received_lsn - latest_end_lsn` (System backlog) | Amount of WAL data pending (bytes) | Overall system capacity, storage, subscriber processing |

**Key Difference**: Apply lag specifically identifies when the **subscriber** is the bottleneck, while receipt lag indicates **network/publisher** issues, and distance lag shows the **overall system backlog**.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/