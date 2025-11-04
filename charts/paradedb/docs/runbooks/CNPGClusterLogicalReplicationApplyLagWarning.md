# CNPGClusterLogicalReplicationApplyLagWarning

## Meaning

The `CNPGClusterLogicalReplicationApplyLagWarning` alert indicates that a CloudNativePG cluster with a logical replication subscription has a time delay of more than 60 seconds between receiving data from the publisher and actually applying it. This is calculated as `NOW() - latest_end_time` from `pg_stat_subscription`.

This alert serves as an early warning that the subscriber is experiencing processing difficulties. While not critical yet, sustained apply lag can lead to significant data divergence and eventually trigger critical alerts if not addressed.

Common causes include:

* Moderate CPU or memory pressure on the subscriber.
* Temporary disk I/O contention or periods of high write activity.
* Moderate resource contention with other workloads.
* Periods of high transaction volume from the publisher.
* Sub-optimal configuration of replication worker processes.

## Impact

The cluster remains operational, but queries to the subscriber will return data that is up to 60 seconds stale. The impact on applications depends on their tolerance for data staleness, but most interactive applications will begin to notice the delay.

## Diagnosis

1. From the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard]:

   * In the _Logical Replication_ section, examine the _Apply Lag_ graph. Look at the trend - is it stable, increasing, or fluctuating?
   * Check the _Workload_ section for moderate CPU, memory, or disk I/O utilization.
   * Monitor the trend over time to determine if this is a temporary spike or a growing problem.

2. Connect via psql to assess the current state:

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   Check the apply worker status and current lag:

   ```sql
   SELECT s.subname,
          s.worker_type,
          s.pid,
          s.latest_end_time,
          NOW() - s.latest_end_time AS apply_lag_seconds,
          s.received_lsn,
          s.latest_end_lsn,
          pg_size_pretty(pg_wal_lsn_diff(s.received_lsn, s.latest_end_lsn)) AS buffered_lag,
          a.state, a.wait_event_type, a.wait_event
   FROM pg_stat_subscription AS s
   LEFT JOIN pg_stat_activity AS a ON a.pid = s.pid
   WHERE s.worker_type = 'apply'
   ORDER BY s.subname;
   ```

   * Apply lag between 60-300 seconds indicates the subscriber is struggling but keeping up.
   * Fluctuating lag suggests periodic performance issues rather than sustained problems.
   * Check if `wait_event_type` indicates resource contention (Lock, LWLock, etc.).

3. Check for resource-consuming sessions:

   ```sql
   SELECT pid, now() - query_start AS duration, query, state,
          usename, application_name
   FROM pg_stat_activity
   WHERE state != 'idle'
     AND pid NOT IN (SELECT pid FROM pg_stat_subscription WHERE pid IS NOT NULL)
     AND now() - query_start > INTERVAL '5 minutes'
   ORDER BY duration DESC
   LIMIT 10;
   ```

4. Check recent subscription performance trends:

   ```sql
   SELECT subname,
          apply_error_count,
          sync_error_count,
          CASE
            WHEN stats_reset > NOW() - INTERVAL '1 day' THEN stats_reset
            ELSE NULL
          END as recent_reset
   FROM pg_stat_subscription_stats;
   ```

## Mitigation

For warning-level apply lag, consider these mitigation strategies:

* **Monitor the trend**: If lag is stable or decreasing, continue monitoring without immediate action.
* **Resource optimization**:
  * Review and optimize long-running queries on the subscriber.
  * Consider scheduling heavy workloads during off-peak hours if possible.
  * Ensure regular `ANALYZE` operations to maintain accurate statistics.

* **Configuration tuning**:
  * If this is a recurring issue, consider increasing `max_logical_replication_workers`:
    ```bash
    # Helm: cluster.postgresql.parameters.max_logical_replication_workers
    # Terraform: paradedb.postgresql.parameters.max_logical_replication_workers
    ```
  * Ensure `max_parallel_workers` is configured appropriately for the subscriber workload.

* **Performance monitoring**:
  * Set up monitoring alerts for subscriber resource utilization.
  * Track apply lag trends over time to identify patterns or degradation.
  * Consider adding more detailed metrics for specific types of operations.

* **Workload management**:
  * If possible, batch large operations on the publisher to reduce replication load.
  * Review publication filters to ensure only necessary data is being replicated.
  * Consider read replicas for heavy analytical queries to reduce load on the subscriber.

* **Preventive measures**:
  * Regular maintenance: vacuum, analyze, and index maintenance on the subscriber.
  * Monitor disk space and I/O performance proactively.
  * Plan capacity scaling based on observed growth patterns.

**When to escalate to critical response**:
- Apply lag consistently above 200 seconds
- Rapidly increasing lag trend
- Frequent error counts in `pg_stat_subscription_stats`
- Resource utilization consistently above 80%

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Apply Lag (Warning)** | `NOW() - latest_end_time` (Subscriber performance) | Time since data was last **applied** (60s+) | Subscriber resources, workload management, configuration tuning |
| **Apply Lag (Critical)** | `NOW() - latest_end_time` (Subscriber performance) | Time since data was last **applied** (300s+) | Subscriber scaling, immediate performance issues, blocking queries |
| **Receipt Lag (Warning)** | `NOW() - last_msg_receipt_time` (Network connectivity) | Time since last data **received** (60s+) | Network performance, publisher load |
| **Distance Lag (Warning)** | `received_lsn - latest_end_lsn` (System backlog) | Amount of WAL pending (1GB+) | Overall system capacity, storage planning |

**Key Difference**: Apply lag warning gives you early insight into **subscriber performance issues** before they become critical, allowing for proactive optimization rather than reactive emergency response.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/