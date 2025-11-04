# CNPGClusterLogicalReplicationDistanceWarning

## Meaning

The `CNPGClusterLogicalReplicationDistanceWarning` alert is triggered when a CloudNativePG cluster with a logical replication subscription has an LSN distance lagging behind its publication by more than 1 GiB. This is calculated as `received_lsn - latest_end_lsn` from `pg_stat_subscription`.

This alert indicates that despite having a good connection between the publisher and the subscriber, the subscriber is not able to process changes from the publisher quickly enough. Here are some common reasons why this can happen:

* The subscriber is under heavy load and cannot process changes fast enough.
* The subscriber cannot flush changes to disk quickly enough.
* Insufficient `max_logical_replication_workers` configured on the subscriber.
* Insufficient `max_worker_processes` configured on the subscriber.
  `max_worker_processes` must be greater than or equal to: `max_parallel_workers + max_parallel_maintenance_workers + max_logical_replication_workers`.
* A recent failover or restart of the subscriber, causing temporary lag while it catches up with the publisher.

## Impact

The cluster remains operational, but queries to the subscriber will return stale data.

## Diagnosis

1. From the [CloudNativePG Grafana Dashboard][cloudnativepg-dashboard]:

   * Check the _Cluster Overview_ section for recent failover events. After a failover, replication lag is expected and may take several minutes to resolve, depending on data volume and subscriber load.
   * In the _Logical Replication_ section, examine the _LSN Distance_ graph. Review both the absolute distance and its trend. A decreasing trend indicates recovery, while an increasing trend suggests the problem is worsening.

2. In the _CloudNativePG Parameters_ section of the dashboard, verify the configuration values for `max_logical_replication_workers` and `max_worker_processes`. Ensure `max_worker_processes` is sized according to the formula above.

3. Connect via psql to check the logical replication subscription status:

  ```sh
  kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
  ```

  Check `pg_stat_subscription` for the subscription status:

  ```sql
  SELECT s.subname,
         s.worker_type,
         s.pid,
         s.received_lsn, s.latest_end_lsn,
         s.last_msg_send_time, s.last_msg_receipt_time,
         a.state, a.wait_event_type, a.wait_event,
         a.query,
         pg_blocking_pids(a.pid) AS blocked_by
  FROM pg_stat_subscription AS s
  LEFT JOIN pg_stat_activity   AS a ON a.pid = s.pid
  ORDER BY s.subname, s.worker_type;
  ```

   * If no rows are returned, the subscription is not active. Check the PostgreSQL logs for errors related to the subscription.
   * Run the query several times, about 30 seconds apart. Healthy systems should show advancing `received_lsn`, `latest_end_lsn`, `last_msg_send_time`, and `last_msg_receipt_time`.
   * A growing gap between `latest_end_lsn` and `received_lsn`, or an increasing `now() - latest_end_time`, indicates the subscription is falling behind.
   * Stale `last_msg_*` times (minutes or hours old) indicate connectivity to the publisher is down or stuck.
   * If `wait_event_type = 'Lock'`, the apply worker is blocked by another transaction. Use `pg_blocking_pids(pid)` to identify the blocking session.
   * If `wait_event_type = 'LWLock'` and `wait_event = 'ReplicationSlotIO'`, the worker is waiting on replication slot operations, which may indicate slot metadata contention or disk I/O bottlenecks.

  To check which process is blocking an apply worker, run:

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
         sa.usename, sa.state, sa.wait_event_type, sa.wait_event, sa.query
  FROM blk b
  JOIN pg_stat_activity sa ON sa.pid = b.blocker;
  ```

  * If the blocking PID is not found in `pg_stat_activity`, it may have completed. Check PostgreSQL logs for recent activity.

   * During initial synchronization, you can check `pg_subscription_rel` to monitor progress and identify reasons the subscription may be stuck:

  ```sql
  SELECT sub.subname,
         sr.srrelid::regclass AS table_name,
         sr.srsubstate,        -- i,d,f,s,r
         sr.srsublsn
  FROM pg_subscription_rel AS sr
  JOIN pg_subscription     AS sub ON sub.oid = sr.srsubid
  ORDER BY sub.subname, table_name;
  ```

   * Conflicts such as constraint violations, permission issues, or Row Level Security (RLS) policies can cause the apply worker to stop processing changes. Check subscription stats by running:

  ```sql
  SELECT subname, apply_error_count, sync_error_count, stats_reset
  FROM pg_stat_subscription_stats;
  ```

4. Check the PostgreSQL logs for any errors related to the subscription:

  ```sh
  kubectl logs -f --all-containers --namespace NAMESPACE pod/POD_NAME
  ```

5. If you suspect slot or back-pressure issues, check the slot health on the publisher:

  ```sql
  SELECT slot_name, slot_type, plugin,
         active, active_pid,
         restart_lsn, confirmed_flush_lsn,
         wal_status
  FROM pg_replication_slots
  ORDER BY slot_name;
  ```

## Mitigation

Depending on the cause, try the following:

* If the subscriber has recently restarted or failed over, allow time for it to catch up with the publisher. The time required depends on the volume of data and the subscriber's load.
* Adjust the `max_logical_replication_workers` and `max_worker_processes` parameters on the subscriber to allow more parallel workers. Edit `paradedb.postgresql.parameters` in the configuration and apply the changes. Avoid using `kubectl edit` on the `paradedb` CNPG Cluster resource directly, as changes will be overwritten by the next configuration update.
* If the subscriber is under heavy load, consider scaling up its resources (CPU, memory, etc.) or offloading queries to read replicas where possible.
* If the subscriber cannot flush changes to disk quickly enough, consider using a storage class with higher IOPS and throughput. Update the `paradedb.storage.storageClass` and `paradedb.walStorage.storageClass` parameters in the configuration. This requires rebuilding instances one by one, so schedule during a maintenance window.
* If the apply worker is blocked by a conflict, check the logs for the error indicating the LSN where the conflicting transaction ends.

  ```sh
  kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")
  kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.message | contains("finished at"))'
  ```

  For example, given the following message:

  ```
  {
    "level": "info",
    "ts": "2025-09-08T18:38:24.253485988Z",
    "logger": "postgres",
    "msg": "record",
    "logging_pod": "paradedb-2",
    "record": {
      "log_time": "2025-09-08 18:38:24.252 UTC",
      "process_id": "11401",
      "session_id": "68bf22a0.2c89",
      "session_line_num": "3",
      "session_start_time": "2025-09-08 18:38:24 UTC",
      "virtual_transaction_id": "114/0",
      "transaction_id": "0",
      "error_severity": "LOG",
      "sql_state_code": "00000",
      "message": "logical replication completed skipping transaction at LSN 0/94000380",
      "context": "processing remote data for replication origin \"pg_18726\" during message type \"COMMIT\" in transaction 860, finished at 0/94000380",
      "backend_type": "logical replication apply worker",
      "query_id": "0"
    }
  }
  ```

  You can determine the LSN where the conflicting transaction ends from the log message. In this case, it is `0/94000380`.

   Advance the subscription to skip the conflicting transaction by running:

  ```sql
  ALTER SUBSCRIPTION mysubscription SKIP (lsn = '0/94000380');
  ```

   Verify that the subscription has advanced:

  ```sql
  SELECT subname, subskiplsn, subenabled FROM pg_subscription;
  ```

   Re-enable the subscription if it was disabled due to errors:

  ```sql
  ALTER SUBSCRIPTION mysubscription ENABLE;
  ```

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Distance Lag (Warning)** | `received_lsn - latest_end_lsn` (System backlog) | Amount of WAL data pending (1GB+) | Overall system capacity, storage planning |
| **Apply Lag (Warning)** | `NOW() - latest_end_time` (Subscriber performance) | Time since data was last **applied** (60s+) | Subscriber resources, workload management, configuration tuning |
| **Receipt Lag (Warning)** | `NOW() - last_msg_receipt_time` (Network connectivity) | Time since last data **received** (60s+) | Network performance, publisher load |
| **Distance Lag (Critical)** | `received_lsn - latest_end_lsn` (System backlog) | Amount of WAL data pending (10GB+) | Overall system capacity, storage, subscriber processing |

**Key Difference**: Distance lag warning provides early detection of **system backlog accumulation** before it becomes critical, making it ideal for proactive capacity planning and resource allocation before storage or performance issues escalate.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/
